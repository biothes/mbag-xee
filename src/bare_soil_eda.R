library(readr)
library(dplyr)
library(ggplot2)

baresoil <- read_csv(
  "outputs/output_analysis/bare_soil_analysis_v2.csv") %>%
  janitor::clean_names()

glimpse(baresoil)

baresoil %>%
  ggplot() +
  geom_line(
    aes(x = period, y = percent_bare_soil, group = pointid),
    alpha = 0.2
  ) +
  facet_wrap(~year)

baresoil %>%
  ggplot() +
  geom_line(
    aes(x = factor(year), y = percent_bare_soil, group = pointid),
    alpha = 0.2
  ) +
  facet_wrap(~period)

library(terra)
library(fs)
rasterspath <- "Z:/Projects/PRJ_MBAG/4d_bwk/Rasters telcirkels"
tifs <- fs::dir_ls(rasterspath, glob = "*.tif")
# example plot for one raster
ndvi <- rast(tifs[1])
plot(ndvi)
