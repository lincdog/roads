from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from shapely import geometry
from random import shuffle

import geopandas as gpd
import pandas as pd
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
    sidelength: float = 0
    chunksize: int = 0
    n_workers: int = 0

    area_total: float = 0
    area_used: float = 0
    area_with_intersects: float = 0
    area_frac_with_intersects: float = 0
        
    frac_blocks: float = 0
    n_blocks_used: int = 0
    n_blocks_with_intersects: int = 0
    n_frac_with_intersections: float = 0
        
    time_make_blocks: timedelta = 0
    time_get_intersections: timedelta = 0
    
    
        
    
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
        
        block_list_in_edge = []
        
        for bstart in np.arange(0, len(blocks_arr), chunksize):
            blocks = gpd.GeoSeries(
                data=blocks_arr[bstart:bstart+chunksize], 
                crs=self.road_data_m.crs
            )
            blocks_in_edge = blocks.intersection(self.edge)
            blocks_in_edge = blocks_in_edge[~blocks_in_edge.is_empty]
            
            n_blocks += len(blocks_in_edge)
            block_list_in_edge.append(blocks_in_edge)
            
            if n_blocks >= n_blocks_goal:
                break
            
        self.blocks = pd.concat(block_list_in_edge)
        self.n_blocks = len(self.blocks)
        self.area_blocks = self.blocks.area.sum()
        
    def get_intersections(
        self,
        chunksize=250,
        max_workers=6,
    ):
        n_intersections = 0
        area_intersections = 0
        
        futures = []
                        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            for start_index in range(0, self.n_blocks, chunksize):
                future = executor.submit(
                    map_count_intersections, 
                    self.blocks.values[start_index:start_index+chunksize],
                    self.all_roads
                )
                futures.append(future)

            for i, f in enumerate(as_completed(futures)):
                n_ints, a_ints = f.result()
                #print(f'{i+1}: {n_ints}, {a_ints} m^2')
                
                n_intersections += n_ints
                area_intersections += a_ints
                
        self.n_intersections = n_intersections
        self.area_intersections = area_intersections
        
        return (n_intersections, self.area_intersections)
        
        
class StateAnalysis:
    
    def __init__(self, state_name):
        self.state_data = StateData(state_name)
        
        self.state_roads_file = self.state_data.statewide_file_path('prisecroads', '.shp')
        self.state_edge_file = self.state_data.statewide_file_path('cd118', '.shp')
        
        self.state_maps = StateMaps(self.state_roads_file, self.state_edge_file)
        
        self.result = dict(
            state_name=state_name,
            area_total=self.state_maps.area
        )
        
    def run_analysis(
        self,
        block_sidelength,
        block_frac=None,
        block_chunksize=10000,
        int_chunksize=250,
        int_max_workers=6
    ):
        self.result['sidelength'] = block_sidelength
        self.result['frac_blocks'] = block_frac
        
        block_start = datetime.now()
        
        self.state_maps.make_blocks(
            sidelength=block_sidelength,
            frac=block_frac,
            chunksize=block_chunksize
        )
        
        block_end = datetime.now()
        
        self.result['time_make_blocks'] = block_end - block_start
        
        self.result['n_blocks_used'] = self.state_maps.n_blocks
        self.result['area_used'] = self.state_maps.area_blocks
        
        self.result['chunksize'] = int_chunksize
        self.result['n_workers'] = int_max_workers
        
        int_start = datetime.now()
        
        (n_ints, a_ints) = self.state_maps.get_intersections(
            chunksize=int_chunksize,
            max_workers=int_max_workers
        )
        
        int_end = datetime.now()
        
        self.result['time_get_intersections'] = int_end - int_start
        
        self.result['n_blocks_with_intersects'] = n_ints
        self.result['n_frac_with_intersects'] = n_ints / self.result['n_blocks_used']
        self.result['area_with_intersects'] = a_ints
        self.result['area_frac_with_intersects'] = a_ints / self.result['area_used']
        
        return self.result
        
        
        
        