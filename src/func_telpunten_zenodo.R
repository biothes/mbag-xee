#For checking environment
# print(.libPaths())
# print(installed.packages())

library(inborutils) #zen4r gebruiken


#Check if argument is passed, otherwise use a default path
#trailingOnly:only arguments after --args are returned
args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 0) {
  stop("No path provided to store the file.")
} else {
  download_path <- args[1]
}

inborutils::download_zenodo(
  doi = '10.5281/zenodo.10890741', #random file als placeholder
  path = download_path) 

print('File was downloaded')