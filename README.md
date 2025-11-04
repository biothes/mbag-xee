# MBAG-XEE
Maken van vegetatie-index tijdreeksen voor telpunten met gebruik van [Xarray Earth Engine](https://github.com/google/Xee) (XEE)

Om tijdsreeksen af te halen volstaat het om drie opeenvolgende scripts te runnen, deze scripts zijn aangeduid met cijfers 1-3.

Citation info
--
Vanpoucke, K., & Heremans, S. (2025). MBAG-XEE [Computer software]. https://github.com/biothes/mbag-xee

01-processing_geometries.R
--
Dit script bestaat uit drie opeenvolgende stappen, met als doel alle percelen in een straal van 300m rond de telpunten vergkrijgen. Hiervoor hebben we eerst het bestand met alle telpunen nodig, dat we van Zenodo kunnen downloaden. Vervolgens wordt er een buffer genomen van 300m rond elk van deze telpunten. In de laatste stap wordt er dan een intersectie genomen tussen deze gebufferde telpunten en de landbouwgebruikspercelen. Elk van de percelen krijgt ook een pointid toegekend, dat overeenstemt met het id van het telpunt.

Om het script zelf te runnen pas je best de verschillende paths aan:
- `download_path`: waar je wilt dat de bestanden van Zenodo terecht komen
- `Q_schijf`: het pad naar de 'opgekuiste' versie van de landbouwgebruikspercelen
- `Q_schijf_output`: het pad naar waar we de geclipte landbouwgebruikspercelen met correcte pointid willen wegschrijven

02-xee_timeseries.ipynb
--
In dit script downloaden we opeenvolgende stukjes raster rond elk van de telpunten. Hiervoor hebben we de gebufferde telpunten (tc = telcirkels) nodig die we in het vorige script hebben weggeschreven naar de Q-schijf. In de processing for-loop wordt voor elk telpunt een rasters opgehaald in een tijdsreeks tussen de start- en einddatum, deze rasters worden in een stack per telpunt weggeschreven naar de output folder.

Om het script zelf te runnen pas je best de settings vanboven in de notebook aan:
- `start`: de startdatum van de tijdsreeks, die enkele maanden vroeger ligt dan de tijdsspanne die we onderzoeken, zodat we achteraf kunnnen interpoleren
- `end`: de einddatum van de tijdsreeks, die enkele maanden later ligt dan de tijdsspanne die we onderzoeken, zodat we achteraf kunnnen interpoleren
- `start_wdw`: de startdatum van de tijdsreeks
- `end_wdw`: de eindatum van de tijdseeks
- `vi_str`: de index die we willen downloaden, momenteel zijn `bsi` en `ndvi` ondersteund
- `sg_filter`: T/F, Savitzky-Golay filter toepassen is standaard, dus best op `True` laten. De filter zorgt voor het smoothen van de data.
- `output_folder`: het pad naar waar de bestanden worden weggeschreven
- `export`: T/F, als True dan worden de bestanden effectief weggeschreven naar de `output_folder`
  
03-bare-soil-analysis.ipynb
--
Het doel van dit script is om de rasters die per telpunt werden gedownload om te zetten naar tijdsreeksen per landbouwveld in een buffer van 300m. Hiervooor hebben we de gedownloade rasters nodig uit stap 2 en de geclipte landbouwvelden uit stap 1. Omdat de landbouwvelden per jaar kunnen verschillen, worden deze tijdsreeksen jaar per jaar verwerkt. Bijvoorbeeld, als we in stap 2 tijdsreeksen downloadden tussen 2022-2024, dan gebruiken we de landbouwpercelen uit 2022 om de rasterdata uit 2022 te aggregeren per veld, enzovoort.

Nadat de tijdsreeksen per veld werden geaggregeerd wordt er een berekening gedaan van het percentage naakte bodem in elke telperiode. Voor meer details van deze berekening, kan je kijken naar de `bare_soil_calc`functie in het script `func_processing`. Ook als je de thresholds zou willen aanpassen van wanneer iets als naakte bodem gerekend wordt, kan je dat in deze functie aanpassen.


Om het script zelf te runnen pas je opnieuw de settings aan zoals gewenst:
- `vi_str`: de index waarvan we de data willen verwerken, momenteel zijn `bsi` en `ndvi` ondersteund
- `output_folder`: de plaats naar waar de bestanden wordt weggeschreven
- `path_202x`: het pad naar de juiste bestand met de landbouwgebruikspercelen, stel dat je de tijdsreeksen van 2025 wilt downloaden, dan maak je hier een nieuwe variabele van. In de cel hieronder maak je dan ook `gdf_2025` aan en voeg je de telperiodes manueel toe in de `periods` dictionary.


## Repository structure
```
├───data
│   ├───raw
│   ├───processed
├───outputs
│   └───output_analysis
└───src
    ├───01-processing_geometries.R
    ├───02-xee-timeseries.ipynb
    ├───func_mask.py
    ├───func_processing.py
    ├───bare_soil_eda.R
    └───...
```
