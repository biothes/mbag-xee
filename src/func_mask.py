import ee

CLOUD_FILTER = 50  #% for filtering the imagecollection
CLD_PRB_THRESH = 50  #% for select clouds and non clouds in S2_Cloud_Probability
NIR_DRK_THRESH = 0.15 #value for detect tge dark pixels
CLD_PRJ_DIST = 3  #cloud projection
BUFFER = 40

def get_s2(aoi, start_date, end_date):
    # Import and filter S2 SR.
    s2_sr_col = (ee.ImageCollection('COPERNICUS/S2_SR')
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', CLOUD_FILTER)))

    # Import and filter s2cloudless.
    s2_cloudless_col = (ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
        .filterBounds(aoi)
        .filterDate(start_date, end_date))

    # Join the filtered s2cloudless collection to the SR collection by the 'system:index' property.
    return ee.ImageCollection(ee.Join.saveFirst('s2cloudless').apply(**{
        'primary': s2_sr_col,
        'secondary': s2_cloudless_col,
        'condition': ee.Filter.equals(**{
            'leftField': 'system:index',
            'rightField': 'system:index'
        })
    }))

def addNDVI(image):
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('ndvi')
    return image.multiply(0.0001).addBands(ndvi).copyProperties(image, ['system:time_start'])


def addBSI(image):
    # Calculate BSI using the formula:
    # BSI = ((B11 + B04) - (B08 + B02)) / ((B11 + B04) + (B08 + B02))
    bsi = image.expression(
        '((B11 + B04) - (B08 + B02)) / ((B11 + B04) + (B08 + B02))',
        {
            'B11': image.select('B11'),  # Assuming these are the correct band designations for Sentinel-2
            'B04': image.select('B4'),   # Red
            'B08': image.select('B8'),   # NIR
            'B02': image.select('B2')    # Blue
        }
    ).rename('bsi')

    # Scale the original image bands (this scaling factor of 0.0001 is typically
    # used for Sentinel-2 imagery to convert from Digital Number to reflectance)
    scaled_image = image.multiply(0.0001)

    # Add the BSI band to the scaled image and copy properties
    return scaled_image.addBands(bsi).copyProperties(image, ['system:time_start'])



def add_cloud_bands(img):
    # Get s2cloudless image, subset the probability band.
    cld_prb = ee.Image(img.get('s2cloudless')).select('probability')

    # Condition s2cloudless by the probability threshold value.
    is_cloud = cld_prb.gt(50).rename('clouds')

    # Add the cloud probability layer and cloud mask as image bands.
    return img.addBands(ee.Image([cld_prb, is_cloud]))

def add_shadow_bands(img):
    # Identify water pixels from the SCL band.
    not_water = img.select('SCL').neq(6)

    # Identify dark NIR pixels that are not water (potential cloud shadow pixels).
    SR_BAND_SCALE = 1e4
    dark_pixels = img.select('B8').lt(NIR_DRK_THRESH*SR_BAND_SCALE).multiply(not_water).rename('dark_pixels')

    # Determine the direction to project cloud shadow from clouds (assumes UTM projection).
    shadow_azimuth = ee.Number(90).subtract(ee.Number(img.get('MEAN_SOLAR_AZIMUTH_ANGLE')));

    # Project shadows from clouds for the distance specified by the CLD_PRJ_DIST input.
    cld_proj = (img.select('clouds').directionalDistanceTransform(shadow_azimuth, CLD_PRJ_DIST*10)
        .reproject(**{'crs': img.select(0).projection(), 'scale': 100})
        .select('distance')
        .mask()
        .rename('cloud_transform'))

    # Identify the intersection of dark pixels with cloud shadow projection.
    shadows = cld_proj.multiply(dark_pixels).rename('shadows')

    # Add dark pixels, cloud projection, and identified shadows as image bands.
    return img.addBands(ee.Image([dark_pixels, cld_proj, shadows]))


def add_cld_shdw_mask(img):
    # Add cloud component bands.
    img_cloud = add_cloud_bands(img)

    # Add cloud shadow component bands.
    img_cloud_shadow = add_shadow_bands(img_cloud)

    # Combine cloud and shadow mask, set cloud and shadow as value 1, else 0.
    is_cld_shdw = img_cloud_shadow.select('clouds').add(img_cloud_shadow.select('shadows')).gt(0)

    # Remove small cloud-shadow patches and dilate remaining pixels by BUFFER input.
    # 20 m scale is for speed, and assumes clouds don't require 10 m precision.
    is_cld_shdw = (is_cld_shdw.focalMin(2).focalMax(BUFFER*2/20)
        .reproject(**{'crs': img.select([0]).projection(), 'scale': 20})
        .rename('cloudmask'))

    # Add the final cloud-shadow mask to the image.
    return img_cloud_shadow.addBands(is_cld_shdw)

#apply the new mask
def apply_mask(img):
  mask=img.select('cloudmask')
  inv_mask=mask.eq(0)
  return img.updateMask(inv_mask).multiply(0.0001)\
      .select('B.*')\
      .copyProperties(img, ['system:time_start'])