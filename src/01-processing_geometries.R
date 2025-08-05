library(inborutils)
library(sf)
library(dplyr)
library(qgisprocess)

setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
print(getwd())



#---- Functions ----
download_from_zenodo <- function(download_path, zenodo_doi, file_name) {
  # Create the full file path
  file_path <- file.path(download_path, file_name)
  
  # Check if the file already exists in the download directory
  if (file.exists(file_path)) {
    print("File already exists at the specified path.")
  } else {
    # Download the file if it doesn't exist
    inborutils::download_zenodo(
      doi = zenodo_doi,
      path = download_path
    )
    print('File was downloaded')
  }
}



telpunt_to_telcirkel <- function(input_csv, buffer_distance = 300) {
  
  # Step 1: Read the CSV file into a dataframe
  df_pts <- read.csv(input_csv)
  
  # Step 2: Create an sf object with 'geometry' column based on the coordinates (assuming x and y coordinates are in 'x_coord' and 'y_coord')
  df_pts <- df_pts %>%
    st_as_sf(coords = c('x_coord', 'y_coord'), crs = df_pts$crs[1])
  
  # Step 3: Buffer the points by the specified distance (default 300 meters)
  df_pts_buffered <- st_buffer(df_pts, dist = buffer_distance)
  
  # Step 4: Write to file for visualization
  st_write(df_pts_buffered, dsn = "../data/processed/telcirkels_viz.gpkg", append=FALSE)
  
  # Step 5: Return points
  return(df_pts_buffered)
}

#--

intersect_parcels <- function(layer_name, telcirkels) {
  
  # Read in the fields
  parcels <- st_read(
    file.path(Q_schijf, paste0(layer_name, '.gpkg')),
    layer = layer_name,
    query = paste0("SELECT REF_ID, GRAF_OPP, GWSGRPH_LB, LANDBSTR, jaar, geom FROM ", layer_name) #, " LIMIT 500"
  )
  
  # Weglaten van landbouwinfrastructuur uit parcels (hiervoor willen we geen tijdsreeksen)
  parcels_subset <- parcels |> 
    filter(GWSGRPH_LB != 'Landbouwinfrastructuur')
  
  
  # QGIS processing
  
  # 1) Intersection fields
  result <- qgis_run_algorithm(
    algorithm = 'native:intersection',
    INPUT = parcels_subset,
    OVERLAY = telcirkels,
    .quiet = TRUE
  )
  
  # 2) Assign pointid to the parcels
  result <- qgis_run_algorithm(
    "native:joinattributesbylocation",
    INPUT = result$OUTPUT,
    JOIN = telcirkels,
    PREDICATE = 'contain',
    JOIN_FIELDS = 'pointid',
    METHOD = 0, # for every match, create a separate geometry
    OUTPUT = file.path(Q_schijf_output, paste0(layer_name, '_clip', '.gpkg')),
    .quiet = TRUE
  )
}

#---- Execute ----

# Download telpunten van Zenodo
download_path <- '../data/raw'
zenodo_doi <- '10.5281/zenodo.16614734'
file_name <- 'steekproef_avimap_mbag_mas.csv'

download_from_zenodo(download_path, zenodo_doi, file_name)


# Omzetten van de telpunten naar telcirkels(buffer)
input_csv <- file.path(download_path, file_name)

df_tc <- telpunt_to_telcirkel(input_csv, buffer_distance = 300)


# Nu QGIS processing gebruiken om de verschillende kaartlagen te clippen naar df_tc
Q_schijf <- 'Q:/Projects/PRJ_MBAG/4a_mas/verzamelaanvraag/processed'
Q_schijf_output <- 'Q:/Projects/PRJ_MBAG/4d_bwk/project-telcirkels'


intersect_parcels(layer_name = 'landbouwgebruikspercelen_cut_bo_2022', telcirkels = df_tc)
intersect_parcels(layer_name = 'landbouwgebruikspercelen_cut_bo_2023', telcirkels = df_tc)
intersect_parcels(layer_name = 'landbouwgebruikspercelen_cut_bo_2024', telcirkels = df_tc)



