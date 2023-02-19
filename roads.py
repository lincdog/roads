from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from shapely import geometry
from random import shuffle

import geopandas as gpd
import numpy as np
import warnings


STATES = ('alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado', 'connecticut',
         'delaware', 'district of columbia', 'florida', 'georgia', 'hawaii', 'idaho', 'illinois',
         'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana', 'maine', 'maryland', 'massachusetts', 'michigan',
         'minnesota', 'mississippi', 'missouri', 'montana', 'nebraska', 'nevada', 'new hampshire', 
         'new jersey', 'new mexico', 'new york', 'north carolina', 'north dakota', 'ohio', 'oklahoma',
         'oregon', 'pennsylvania', 'rhode island', 'south carolina', 'south dakota', 'tennessee', 
         'texas', 'utah', 'vermont', 'virginia', 'washington', 'west virginia', 'wisconsin', 'wyoming')

NUMS = (1, 2, 4, 5, 6, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26,
       27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 44, 45, 46, 47, 48, 
       49, 50, 51, 53, 54, 55, 56)

file_prefix = 'tl_rd22'


def f_num(num):
    if isinstance(num, str):
        return num
    elif isinstance(num, int):
        return f'{num:02d}'
    else:
        raise TypeError('Value must be string or integer')

        
def state_folder(state, num):
    return '_'.join([f_num(num), state.upper().replace(' ', '_')])


state2num = {s: f_num(n) for s, n in zip(STATES, NUMS)}

state2state_folder = {s: state_folder(s, n) for s, n in zip(STATES, NUMS)}


class StateData:
    def __init__(
        self,
        state,
        state_folder_location='us_tiger_roads'
    ):
        self.state = state.lower()
        self.num = state2num[self.state]
        self.state_folder_location = state_folder_location
        self.state_folder_name = state2state_folder[self.state]
        self.state_folder_path = Path(self.state_folder_location, self.state_folder_name)
    
    def statewide_filename(
        self,
        tag,
        ext='.shp'
    ):
        if not ext:
            ext = ''
            
        filename = '_'.join([
            file_prefix,
            self.num,
            tag
        ])
        
        filename += ext
        
        return filename
        
    def file_path(
        self,
        filename
    ):
        return self.state_folder_path / filename
    
    def statewide_file_path(
        self,
        tag,
        ext='.shp'
    ):
        return self.state_folder_path / self.statewide_filename(tag, ext)
    

def box_from_coords(minx, miny, sidelen):
    return geometry.Polygon([
        (minx, miny), 
        (minx+sidelen, miny), 
        (minx+sidelen, miny+sidelen), 
        (minx, miny+sidelen)
    ])

def map_count_intersections(blocks, roads):
    intersects = blocks.intersects(roads)
        
    n_intersections = intersects.sum()
    intersects_area = blocks[intersects].area.sum()
    
    return (n_intersections, intersects_area)
  

@dataclass
class IntersectionResult:
    state_name: str
    sidelength: float
    chunksize: int
    n_workers: int

    area_total: float
    area_used: float
    area_with_intersects: float
        
    n_blocks_total: int
    n_blocks_used: int
    n_blocks_with_intersects: int
        
    time_make_blocks: timedelta
    time_get_intersections: timedelta
    
    
        
    
class StateMaps:
    def __init__(
        self,
        road_filename,
        edge_filename
    ):
        self.road_filename = Path(road_filename)
        self.edge_filename = Path(edge_filename)
        
        self.road_data = gpd.read_file(self.road_filename)
        self.road_data_m = self.road_data.to_crs('EPSG:3857')
        self.all_roads = self.road_data_m.unary_union
        self.all_roads_df = gpd.GeoSeries(data=self.all_roads, crs=self.road_data_m.crs)
        
        self.edge_data = gpd.read_file(self.edge_filename)
        self.edge_data_m = self.edge_data.to_crs('EPSG:3857')
        self.edge = self.edge_data_m.unary_union
        self.edge_df = gpd.GeoSeries(data=self.edge, crs=self.edge_data_m.crs)
        
        self.area = self.edge.area
        
        self.bounds = self.edge_data_m.total_bounds
        self.minx, self.miny, self.maxx, self.maxy = self.bounds
        
        self.blocks = gpd.GeoSeries(crs=self.edge_data_m.crs)
        self.n_blocks = 0
        
    def make_blocks(
        self,
        sidelength,
        frac=None,
        chunksize=10000
    ):
        breakpoint()
        
        blocks_arr = []
        
        for x in np.arange(self.minx, self.maxx, sidelength):
            for y in np.arange(self.miny, self.maxy, sidelength):
                blocks_arr.append(box_from_coords(x, y, sidelength))
        
        shuffle(blocks_arr)
        
        frac = frac or 1
        if frac < 0 or frac > 1:
            frac = 1
        
        area_goal = frac * self.area
        n_blocks_goal = round(area_goal / blocks_arr[0].area)
        
        n_blocks = 0
        
        for bstart in np.arange(0, len(blocks_arr), chunksize):
            blocks = gpd.GeoSeries(
                data=blocks_arr[bstart:bstart+chunksize], 
                crs=self.road_data_m.crs
            )
            blocks_in_edge = blocks.intersection(self.edge)
            blocks_in_edge = blocks_in_edge[~blocks_in_edge.is_empty]
            
            n_blocks += len(blocks_in_edge)
            self.blocks.append(blocks_in_edge)
            
            if n_blocks >= n_blocks_goal:
                break
   
    def _get_intersections_simple(
        self,
        bounds
    ):
        minx, maxx, miny, maxy = bounds
        result = 0
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # find intersection
            edge_clipped = self.edge_df.clip_by_rect(minx, miny, maxx, maxy)
            # check if nonempty intersection
            if not edge_clipped.is_empty.all():
                roads_in_box = self.all_roads_df.clip_by_rect(minx, miny, maxx, maxy)

                if not roads_in_box.is_empty.all():
                    result = 1
        
        return result

    def get_intersections_simple(
        self,
        sidelength,
        chunksize=1000,
        max_workers=6
    ):
        num_intersections = 0
        
        i = 0
        
        bboxes = []
        
        for x in np.arange(self.minx, self.maxx, sidelength):
            for y in np.arange(self.miny, self.maxy, sidelength):
                bboxes.append((x, y, x+sidelength, y+sidelength))
         
        futures = []
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            num_intersections += sum(executor.map(
                self._get_intersections_simple, 
                bboxes, 
                chunksize=chunksize
            ))
                
        return num_intersections
        
    def get_intersections(
        self,
        chunksize=250,
        max_workers=6,
        n_blocks=None
    ):
        num_intersections = 0
        area_intersections = 0
        
        futures = []
        
        if (not n_blocks) or n_blocks > self.n_blocks:
            n_blocks = self.n_blocks
        
        if n_blocks < 1:
            self.blocks_work = self.blocks.sample(frac=n_blocks)
        else:
            self.blocks_work = self.blocks.sample(n=n_blocks)
            
        self.n_blocks_work = len(self.blocks_work)
        
        print(f'Number of blocks used: {self.n_blocks_work}')
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for start_index in range(0, self.n_blocks_work, chunksize):
                future = executor.submit(
                    map_count_intersections, 
                    self.blocks_work.values[start_index:start_index+chunksize],
                    self.all_roads
                )
                futures.append(future)

            for i, f in enumerate(as_completed(futures)):
                n_ints, a_ints = f.result()
                #print(f'{i+1}: {n_ints}, {a_ints} m^2')
                
                num_intersections += n_ints
                area_intersections += a_ints
                
        self.num_intersections = num_intersections
        self.area_intersections = area_intersections
        
        return (num_intersections, self.area_intersections)
        
        
def init_state_analysis(statename):
    state_data = StateData(statename)
    
    state_roads_file = state_data.statewide_file_path('prisecroads', '.shp')
    state_edge_file = state_data.statewide_file_path('cd118', '.shp')
    
    return StateMaps(state_roads_file, state_edge_file)
        