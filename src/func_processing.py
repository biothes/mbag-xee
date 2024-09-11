import os
import ee
import xee
import geemap
import geopandas as gpd
import numpy as np
import pandas as pd
import xarray
import matplotlib.pyplot as plt
from shapely.geometry import box
from scipy.signal import savgol_filter
import rasterio
from rasterio.features import rasterize

from func_mask import get_s2, add_cld_shdw_mask, apply_mask, addNDVI, addBSI

def time_series(start, end, start_wdw, end_wdw, shape, vi_arg, sg):
    '''
    Function for fetching time series using xee (xarray + google earth engine). These time series get interpolated and further processed in an xarray.
    
    Parameters:
    - start: start date to get the time series from google earth engine (have some buffer around start_wdw, so that)
    - end: end date to get the time series from google earth engine
    - start_wdw: start date of the relevant time window
    - end_wdw: end date of the relevant time window
    - shape: shape
    - vi_arg: welke vegetatie-index, 'ndvi' of 'bsi'
    - sg: apply Savitzky-Golay filter? True or False

    '''

    #-- bbox around geometry
    bbox = box(shape.bounds[0],shape.bounds[1],shape.bounds[2],shape.bounds[3])
    gdf = gpd.GeoDataFrame(geometry=[bbox], crs = 4326).to_crs('EPSG:32631')
    gdf['geometry'] = gdf.geometry.buffer(20)
    roi = geemap.geopandas_to_ee(gdf)
    print('crs roi', gdf.crs)

    #-- Masking
    startDate = ee.Date(start)
    endDate = ee.Date(end)

    s2 = get_s2(roi, startDate, endDate)
    s2_shdw = s2.map(add_cld_shdw_mask)
    s2_mask = s2_shdw.map(apply_mask)
    
    if vi_arg == 'ndvi':
        vi = s2_mask.map(addNDVI)
    elif vi_arg == 'bsi':
        vi = s2_mask.map(addBSI)

    #-- Xarray
    ds = xarray.open_dataset(
        vi.select(vi_arg),
        engine='ee',
        crs= 'EPSG:32631', #'', EPSG:32631
        scale=10,
        geometry=roi.geometry(1),
        ee_mask_value= -9999
    )

    #-- Interpolation
    # Drop time duplicates
    ds = ds.drop_duplicates('time')

    # Select VI band
    if vi_arg == 'ndvi':
        original_time_series = ds.ndvi.chunk('auto')
    elif vi_arg == 'bsi':
        original_time_series = ds.bsi.chunk('auto')

    # Interpolate time series
    time_series_interpolated = original_time_series.interpolate_na('time', use_coordinate=False) #fill gaps
    
    # Regular spacing
    new_time = pd.date_range(start=(start_wdw), end=(end_wdw), freq='10D')
    time_series_regular = time_series_interpolated.interp(time=new_time, method='slinear')

    if sg == True:
        #-- Savgol filter
        # Define a function to apply Savitzky-Golay filter using scipy
        def savgol_filter_func(data, window_length=5, polyorder=2):
            return savgol_filter(data, window_length, polyorder)


        # Apply Savitzky-Golay filter along the 'time' dimension
        filtered_da = xarray.apply_ufunc(
            savgol_filter_func,  # Function to apply
            time_series_regular,  # Input dataset
            input_core_dims=[['time']],  # Specify core dimensions
            dask='parallelized',  # Use parallelized computation if using dask arrays
            output_dtypes=[float],  # Output datatype
            output_core_dims=[['time']],
            vectorize=True,  # Vectorize the operation
            keep_attrs=True)  # Keep the original attributes of the dataset
        
        return filtered_da.transpose('time', 'Y', 'X')

    
    else:

        return time_series_regular



#----------------------------------------------------------------------------------------------------
def extract_polygon_ts(ts_array, pd_row, buffer, crs, time_window):
    '''
    Function for calculating the time series over a polygon, with a DataArray as input.
    
    Parameters:
    - ts_array: xarray.DataArray with the time series
    - pd_row: row input through df.itertuples()
    - buffer: how much inward buffer to aggregate the ndvi values should be taken (to remove edge effects)
    - crs: crs of the xarray & geometry in the row
    - time_window: Year (e.g., 2022) to filter the time series
    '''
        
    # Convert time_window to datetime range for the specified year
    start_date = f'{time_window}-01-01'
    end_date = f'{time_window}-12-31'
    
    # Filter the ts_array to the specified year
    ts_array = ts_array.sel(time=slice(start_date, end_date))
    ts_array = ts_array.rio.set_spatial_dims(x_dim='X', y_dim='Y')
        
    df_ndvi = ts_array.time.to_dataframe()[['time']].reset_index(drop=True) # dataframe with the dates
    
    # Aggregation step
    geometry = pd_row.geometry.buffer(buffer) # buffer before aggregation

    if geometry.is_empty:
        print('Empty geometry')
        df_ndvi['ndvi'] = np.nan
        df_ndvi['REF_ID'] = int(pd_row.REF_ID)
        df_ndvi['pointid'] = pd_row.pointid
        return df_ndvi
    
    elif not geometry.is_valid:
        print('Invalid geometry')
        df_ndvi['ndvi'] = np.nan
        df_ndvi['REF_ID'] = int(pd_row.REF_ID)
        df_ndvi['pointid'] = pd_row.pointid
        return df_ndvi
    
    else:
        ts_array_clip = ts_array.rio.clip([geometry], crs, all_touched = True) #geometry moet in een lijst zitten --> dus loop maken met alle polygons...
        ndvi = ts_array_clip.mean(dim=('X', 'Y')).values

        # Create output dataframe
        df_ndvi['ndvi'] = ndvi
        df_ndvi.insert(0, 'REF_ID', int(pd_row.REF_ID))
        df_ndvi.insert(1, 'pointid', pd_row.pointid)
        #df_ndvi.insert(-1, 'geometry', pd_row.geometry)

        return df_ndvi

#----------------------------------------------------------------------------------------------------

def ts_telcirkel_per_jaar(raster, gdf, year, pointid, df_ts):

    gdf_agg = gdf.loc[(gdf.pointid == pointid) & (gdf.jaar == year)] #.to_crs('EPSG:32631') 

    for row in gdf_agg.itertuples():
        #print(row.geometry)
        crs = gdf.crs

        df_long = extract_polygon_ts(ts_array = raster, pd_row = row, buffer = -10, crs=crs, time_window = year)

        if df_ts.empty:
            df_ts = df_long
        elif not df_long.empty:
            df_ts = pd.concat([df_ts, df_long], axis=0)

    return df_ts
#----------------------------------------------------------------------------------------------------
def bare_soil_calc(gdf):
    '''
    Function for calculating the percentage of bare soil in the 'telcirkel'

    Parameters:
    - gdf with the following columns: REF_ID, pointid, date, ndvi and geometry
    '''

    assert list(gdf.columns) == ['REF_ID', 'pointid', 'date', 'ndvi','geometry']
    # periods buiten functie zetten eigenlijk
    periods = {
    'R1_2022': ('2022-04-01', '2022-04-20'),
    'R2_2022': ('2022-04-21', '2022-05-10'),
    'R3_2022': ('2022-05-11', '2022-06-10'),
    'R4_2022': ('2022-06-21', '2022-07-15'),
    'R1_2023': ('2023-04-01', '2023-04-20'),
    'R2_2023': ('2023-04-21', '2023-05-10'),
    'R3_2023': ('2023-05-11', '2023-06-10'),
    'R4_2023': ('2023-06-21', '2023-07-15')}

    # Initialize a list to store the results
    results = []

    # Perform the analysis for each period and year
    for period_key, (start_date, end_date) in periods.items():
        # filter by date
        period_data = gdf[(gdf['date'] >= start_date) & (gdf['date'] <= end_date)]

        # Calculate mean NDVI for each field within each pointid
        mean_ndvi = period_data.groupby(['pointid', 'REF_ID'])['ndvi'].mean().reset_index()
        mean_ndvi = mean_ndvi.rename(columns = {'ndvi' : 'ndvi_mean'})
        
        # Determine fields with mean NDVI < 0.3 as bare soil
        bare_soil_fields = mean_ndvi[mean_ndvi['ndvi_mean'] < 0.3]
        
        # Join back with period_data to calculate areas
        bare_soil_data = pd.merge(bare_soil_fields, period_data, on=['pointid', 'REF_ID'], how='inner')
        bare_soil_data = gpd.GeoDataFrame(bare_soil_data, geometry = 'geometry')

        # Aggregate area of bare soil and total area for each pointid
        for pointid, group in period_data.groupby('pointid'):
            bare_soil_area = bare_soil_data[bare_soil_data['pointid'] == pointid].geometry.area.sum()
            total_area = group.geometry.area.sum()
            
            # Avoid division by zero
            percent_bare_soil = (bare_soil_area / total_area * 100) if total_area > 0 else 0
            
            year = start_date[:4]  # Extract year from start_date
            results.append({'pointid': pointid, 'year': year, 'period': period_key.split('_')[0], '% bare soil': percent_bare_soil})

    # Convert the results into a DataFrame
    results_df = pd.DataFrame(results)

    return results_df