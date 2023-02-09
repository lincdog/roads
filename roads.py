from pathlib import Path

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
    return '_'.join([f_num(num), state.upper()])

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
    
    
            