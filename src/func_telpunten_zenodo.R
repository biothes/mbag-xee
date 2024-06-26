#For checking environment
# print(.libPaths())
# print(installed.packages())

library(inborutils) #zen4r gebruiken
inborutils::download_zenodo(
  doi = '10.5281/zenodo.10890741', #random file als placeholder
  path = 'C:/Users/kato_vanpoucke/Documents/git/mbag-xee/data/01-telcirkels') 

print('File was downloaded')