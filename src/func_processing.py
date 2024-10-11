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
    gdf['geometry'] = gdf.geometry.buffer(50)
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
        
    df_vi = ts_array.time.to_dataframe()[['time']].reset_index(drop=True) # dataframe with the dates
    
    # Aggregation step
    geometry = pd_row.geometry.buffer(buffer) # buffer before aggregation

    #vi
    vi_str = ts_array.attrs['id']

    if geometry.is_empty:
        #print('Empty geometry')
        df_vi[vi_str] = np.nan
        df_vi['REF_ID'] = int(pd_row.REF_ID)
        df_vi['pointid'] = pd_row.pointid
        return df_vi
    
    elif not geometry.is_valid:
        print('Invalid geometry')
        df_vi[vi_str] = np.nan
        df_vi['REF_ID'] = int(pd_row.REF_ID)
        df_vi['pointid'] = pd_row.pointid
        return df_vi
    
    else:
        ts_array_clip = ts_array.rio.clip([geometry], crs, all_touched = True) #geometry moet in een lijst zitten --> dus loop maken met alle polygons...
        ndvi = ts_array_clip.mean(dim=('X', 'Y')).values

        # Create output dataframe
        df_vi[vi_str] = ndvi
        df_vi.insert(0, 'REF_ID', int(pd_row.REF_ID))
        df_vi.insert(1, 'pointid', pd_row.pointid)
        #df_ndvi.insert(-1, 'geometry', pd_row.geometry)

        return df_vi

#----------------------------------------------------------------------------------------------------

def ts_telcirkel_per_jaar(raster, gdf, year, pointid, df_ts):
    '''
    Function for calculating the time series for all parcels in a counting point.
    
    Parameters:
    - raster: xarray.DataArray with the time series
    - gdf: gdf with all parcels in Flanders for a certain year (should match the year in the 'year' parameter)
    - year: year (e.g., 2022) to filter the time series
    - pointid: id of the counting point we're processing
    - df_ts: the dataframe we are adding the time series for every parcel & pointid combination to
    '''
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
def bare_soil_format(df, gdf_year, year, vi_str):
    '''
    Function to format the df_ts into a gdf, which is the correct formatting for the bare soil calculation.
    
    Parameters:
    - df: dataframe with the time series for every parcel & poinid combination
    - gdf_year: gdf with the parcels that should be added to df
    - year: the year we're doing the processing for
    '''
    assert list(df.columns) == ['pointid', 'REF_ID', 'time', vi_str], "Make sure that these are the column names: ['pointid', 'REF_ID', 'time', vi_str]"
    assert isinstance(year, int), f"Input value must be an integer, got {type(year)} instead."

    # Column rename & parse for the correct year
    df = df.reset_index(drop=True).rename(columns = {'time': 'date'})
    df = df.loc[df.date.dt.year == year]
    gdf_year.REF_ID = gdf_year.REF_ID.astype('int64')

    # Merge the df and gdf
    gdf = df.merge(gdf_year[['REF_ID','pointid','geometry']], on = ['REF_ID','pointid'], how = 'left')
    gdf = gpd.GeoDataFrame(gdf, geometry='geometry')
    #gdf.REF_ID = gdf.REF_ID.astype(int)

    return gdf

#----------------------------------------------------------------------------------------------------
def bare_soil_calc(gdf, vi_str, periods):
    '''
    Function for calculating the percentage of bare soil in the 'telcirkel'

    Parameters:
    - gdf with the following columns: REF_ID, pointid, date, ndvi and geometry
    '''
    
    assert vi_str in ['ndvi','bsi']

    if vi_str == 'ndvi':
        assert list(gdf.columns) == ['pointid', 'REF_ID', 'date', 'ndvi','geometry']
    if vi_str == 'bsi':
        assert list(gdf.columns) == ['pointid', 'REF_ID', 'date', 'bsi','geometry']

    # Initialize a list to store the results
    results = []

    # Perform the analysis for each period and year
    for period_key, (start_date, end_date) in periods.items():
        # filter by date
        period_data = gdf[(gdf['date'] >= start_date) & (gdf['date'] <= end_date)]

        # Calculate mean NDVI for each field within each pointid
        mean_vi = period_data.groupby(['pointid', 'REF_ID'])[vi_str].mean().reset_index()
        mean_vi = mean_vi.rename(columns = {vi_str : 'vi_mean'})
        
        # Determine fields with mean NDVI < 0.3 or mean BSI >0.021 as bare soil
        if vi_str == 'ndvi':
            bare_soil_fields = mean_vi[mean_vi['vi_mean'] < 0.3]
        elif vi_str == 'bsi':
            bare_soil_fields = mean_vi[mean_vi['vi_mean'] > 0.021] #Castaldi et al. (2023)
        
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