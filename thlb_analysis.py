'''
This script generates Timber harvest metrics, mainly areas and volumes, for a specific area of interest (AOI). The AOI can be either a Timber supply Area, an Operating area or other ( FN claimed area,?). Tha main steps are:
    1) Clip the input layers to the AOI extent (VRI, OGMA, THLB,...). Other input layers can be added depending on the scope of the analysis
    2) Perform a spatial overlay of the clipped input layers
    3) Add and populate fields based on defined rules: mature timber, merchantability, areas with harvest constraints..
    4) Calculate THLB areas and volumes
    5) Generate metrics by Licensee or Operating area (summary statistics)

'''
import os
import arcpy
from arcpy import env

# Set environment settings
arcpy.env.overwriteOutput = True
spatialRef = arcpy.SpatialReference(3005)

# Create variables for input layers
BCGWcon = r'Database Connections/BCGW.sde/'
VRI = os.path.join(BCGWcon, "WHSE_FOREST_VEGETATION.VEG_COMP_LYR_R1_POLY")
OGMA = os.path.join(BCGWcon, "WHSE_LAND_USE_PLANNING.RMP_OGMA_NON_LEGAL_ALL_SVW")
Licensees = os.path.join(BCGWcon, "REG_LAND_AND_NATURAL_RESOURCE.FOREST_LICENSEE_OPER_SP")

THLB = r'F:/tko_root/Data_Library/Data_Source/THLB/THLB_TSA_TKO.shp'
# BEC_HLP = os.path.join(BCGWcon, "WHSE_FOREST_VEGETATION.BEC_BIOGEOCLIMATIC_POLY")
# BEC_HLP = r'F:/tko_root/Data_Library/Analysis/THLB/2023/FTBO/AR/shapefiles/BEC_FTBO.shp'
BEC_HLP = r'F:\tko_root\Data_Library\Analysis\THLB\2023\FTBO\AR\THLB_Timber_Inputs.gdb\BEC_FTBO'

# Get parameters from user
WorkGDB = arcpy.GetParameterAsText(0)
AOI = arcpy.GetParameterAsText(1)

# Clip the input layers to the AOI extent
toClip = arcpy.CreateFeatureDataset_management(WorkGDB, "inputs", spatialRef)
inputsPath = os.path.join(WorkGDB, str(toClip))

FCs = [VRI, OGMA, Licensees, THLB, BEC_HLP]

for FC in FCs:
    filePref = os.path.basename(AOI)
    fileName = os.path.basename(FC)
    arcpy.AddMessage("Preparing input layers. Clipping {}".format(fileName))
    arcpy.Clip_analysis(FC, AOI, os.path.join(inputsPath, "{}_{}".format(filePref, fileName)))

# Spatial overlay (union) of input layers
arcpy.env.workspace = inputsPath
unionInputs = arcpy.ListFeatureClasses()
arcpy.AddMessage("Creating the THLB analysis Resultant...spatial overlay (union) in progress.")
thlb_analysis_resultant = os.path.join(WorkGDB, "thlb_analysis_resultant")
arcpy.Union_analysis(unionInputs, thlb_analysis_resultant, "ALL")

# # Check for NULL or empty geometries and delete them
# arcpy.AddMessage("Checking for NULL or empty geometries...")
# with arcpy.da.UpdateCursor(thlb_analysis_resultant, ["SHAPE@"]) as cursor:
#     for row in cursor:
#         if row[0] is None or row[0].pointCount == 0:
#             arcpy.AddMessage("Found NULL or empty geometry. Deleting...")
#             cursor.deleteRow()

# try:
#     arcpy.DeleteIdentical_management(thlb_analysis_resultant, "GEOMETRY")
# except arcpy.ExecuteError:
#     arcpy.AddMessage(arcpy.GetMessages(2))
# except Exception as ex:
#     arcpy.AddMessage(ex.args[0])

# arcpy.AddMessage("Variable thlb_analysis_resultant: {}".format(thlb_analysis_resultant))
# arcpy.DeleteIdentical_management(thlb_analysis_resultant, "GEOMETRY")

# Add new fields to the resultant and populate them
resultantFields = arcpy.ListFields(thlb_analysis_resultant)
newFieldsTXT = ["OGMA", "MATURE", "MERCHANTABILITY"]
newFieldsFLOAT = ["new_AREA_ha", "THLB_area_ha", "THLB_volume_m3"]

for field in newFieldsTXT:
    if field not in [f.name for f in resultantFields]:
        arcpy.AddMessage("Adding field {}".format(field))
        arcpy.AddField_management(thlb_analysis_resultant, field, "TEXT", "", "", 5)

for field in newFieldsFLOAT:
    if field not in [f.name for f in resultantFields]:
        arcpy.AddMessage("Adding field {}".format(field))
        arcpy.AddField_management(thlb_analysis_resultant, field, "DOUBLE")
    else:
        pass

UpdateFields = newFieldsTXT + newFieldsFLOAT + ["NON_LEGAL_OGMA_PROVID", "MATURE_YRS", "PROJ_AGE_1",
                                                "LIVE_STAND_VOLUME_125", "THLB_FACT", "GEOMETRY_Area"]

# Populate the new fields

##arcpy.CalculateField_management (thlb_analysis_resultant,"new_AREA_ha",'!shape.area!@hectares','PYTHON')
##arcpy.CalculateGeometryAttributes_management (thlb_analysis_resultant, ["new_AREA_ha", "AREA"], "" , "HECTARES")
ZONES = ['ICH', 'MS', 'IDF', 'PP']
arcpy.AddMessage("Populating new fields...in progress")

with arcpy.da.UpdateCursor(thlb_analysis_resultant, UpdateFields) as cursor:
    for row in cursor:
        if row[6] != "" or row[6] is None:  # Fills OGMA field
            row[0] = "Y"
        else:
            row[0] = "N"

        # if (row[7] == 'ICH' or row[7] == 'PP' or row[7] == 'IDF' or row[7] == 'MS' and row[8] > 100) or (row[7] == "ESSF" and row[8] > 120):  # Fills MATURE field
        if (row[7] == '>100' and row[8] > 100) or (row[7] == '>120' and row[8] > 120):
            row[1] = "Y"
        else:
            row[1] = "N"

        if row[9] > 100:  # Fills MERCHANTABILITY field (min volume 100m^3)
            row[2] = "Y"
        else:
            row[2] = "N"

        row[3] = row[11] / 10000  # Converts to Hectares

        row[4] = row[3] * row[10]

        if row[9] is None:
            row[9] = 0

        row[5] = row[4] * row[9]

        cursor.updateRow(row)

arcpy.AddMessage("New fields populated")

# Compute summary statistics and export to dbf
arcpy.AddMessage("Computing summary statistics")

AllStats = os.path.join(WorkGDB, "AllStats")
whereClauseAllLicencees = """ "OGMA" = 'N' """ + 'and' + """ "MATURE" = 'Y' """ + 'and' + """"MERCHANTABILITY" = 'Y'"""
lyr_all = arcpy.MakeFeatureLayer_management(thlb_analysis_resultant, "lyr_all")
arcpy.SelectLayerByAttribute_management(lyr_all, "NEW_SELECTION", whereClauseAllLicencees)
arcpy.Statistics_analysis(lyr_all, AllStats, [["THLB_area_ha", "SUM"], ["THLB_volume_m3", "SUM"]],
                          "LICENSEE_OPER_AREAS_NAME")
arcpy.Delete_management(lyr_all)
arcpy.AddMessage("Created summary statistics for All Licensees")

BCTSStats = os.path.join(WorkGDB, "BCTSStats")
whereClauseBCTS_only = """ "OGMA" = 'N' """ + 'and' + """ "MATURE" = 'Y' """ + 'and' + """ "MERCHANTABILITY" = 'Y' """ + 'and' + """ "LICENSEE_OPER_AREAS_NAME" = 'BC Timber Sales - Kootenay' """
lyr_BCTS = arcpy.MakeFeatureLayer_management(thlb_analysis_resultant, "lyr_BCTS")
arcpy.SelectLayerByAttribute_management(lyr_BCTS, "NEW_SELECTION", whereClauseBCTS_only)
arcpy.Statistics_analysis(lyr_BCTS, BCTSStats, [["THLB_area_ha", "SUM"], ["THLB_volume_m3", "SUM"]],
                          "LICENSEE_OPER_AREAS_TENURE")
arcpy.Delete_management(lyr_BCTS)
arcpy.AddMessage("Created summary statistics for a BCTS Op Areas")

table_outputs = r"F:/tko_root/Data_Library/Analysis/THLB/2023/FTBO/"
# Convert summary statistics to Excel
excel_output_all = os.path.join(table_outputs, "AllStats.xls")
arcpy.TableToExcel_conversion(AllStats, excel_output_all)
arcpy.AddMessage("Converted summary statistics for All Licensees to Excel")

excel_output_BCTS = os.path.join(table_outputs, "BCTSStats.xls")
arcpy.TableToExcel_conversion(BCTSStats, excel_output_BCTS)
arcpy.AddMessage("Converted summary statistics for BCTS Op Areas to Excel")

arcpy.AddMessage("THLB analysis completed successfully")


