import logging
import os
import re

import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin


#
# TotalSegmentator
#
#

class TotalSegmentator(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Total Segmentator"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Andras Lasso (PerkLab, Queen's University)"]
        self.parent.helpText = """
3D Slicer extension for fully automatic whole body CT segmentation using "TotalSegmentator" AI model.
See more information in the <a href="https://github.com/lassoan/SlicerTotalSegmentator">extension documentation</a>.
"""
        self.parent.acknowledgementText = """
This file was originally developed by Andras Lasso (PerkLab, Queen's University).
The module uses <a href="https://github.com/wasserth/TotalSegmentator">TotalSegmentator</a>.
If you use the TotalSegmentator nn-Unet function from this software in your research, please cite:
Wasserthal J., Meyer M., , Hanns-Christian Breit H.C., Cyriac J., Shan Y., Segeroth, M.:
TotalSegmentator: robust segmentation of 104 anatomical structures in CT images.
https://arxiv.org/abs/2208.05868
"""
        slicer.app.connect("startupCompleted()", self.configureDefaultTerminology)

    def configureDefaultTerminology(self):
        moduleDir = os.path.dirname(self.parent.path)
        totalSegmentatorTerminologyFilePath = os.path.join(moduleDir, 'Resources', 'SegmentationCategoryTypeModifier-TotalSegmentator.term.json')
        tlogic = slicer.modules.terminologies.logic()
        self.terminologyName = tlogic.LoadTerminologyFromFile(totalSegmentatorTerminologyFilePath)

#
# TotalSegmentatorWidget
#

class TotalSegmentatorWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/TotalSegmentator.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = TotalSegmentatorLogic()
        self.logic.logCallback = self.addLog

        for task in self.logic.tasks:
            self.ui.taskComboBox.addItem(self.logic.tasks[task]['label'], task)

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.ui.inputVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.fastCheckBox.connect('toggled(bool)', self.updateParameterNodeFromGUI)
        self.ui.cpuCheckBox.connect('toggled(bool)', self.updateParameterNodeFromGUI)
        self.ui.useStandardSegmentNamesCheckBox.connect('toggled(bool)', self.updateParameterNodeFromGUI)


        self.ui.taskComboBox.currentTextChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.outputSegmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.outputSegmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.ui.segmentationShow3DButton.setSegmentationNode)

        # Buttons
        self.ui.packageInfoUpdateButton.connect('clicked(bool)', self.onPackageInfoUpdate)
        self.ui.packageUpgradeButton.connect('clicked(bool)', self.onPackageUpgrade)
        self.ui.setLicenseButton.connect('clicked(bool)', self.onSetLicense)
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()

    def enter(self):
        """
        Called each time the user opens this module.
        """
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self):
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
        self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    def onSceneStartClose(self, caller, event):
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event):
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
          self.initializeParameterNode()

    def initializeParameterNode(self):
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

        # Select default input nodes if nothing is selected yet to save a few clicks for the user
        if not self._parameterNode.GetNodeReference("InputVolume"):
            firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
            if firstVolumeNode:
                self._parameterNode.SetNodeReferenceID("InputVolume", firstVolumeNode.GetID())

    def setParameterNode(self, inputParameterNode):
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if inputParameterNode:
            self.logic.setDefaultParameters(inputParameterNode)

        # Unobserve previously selected parameter node and add an observer to the newly selected.
        # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
        # those are reflected immediately in the GUI.
        if self._parameterNode is not None:
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        # Update node selectors and sliders
        self.ui.inputVolumeSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputVolume"))
        task = self._parameterNode.GetParameter("Task")
        self.ui.taskComboBox.setCurrentIndex(self.ui.taskComboBox.findData(task))
        self.ui.fastCheckBox.checked = self._parameterNode.GetParameter("Fast") == "true"
        self.ui.cpuCheckBox.checked = self._parameterNode.GetParameter("CPU") == "true"
        self.ui.useStandardSegmentNamesCheckBox.checked = self._parameterNode.GetParameter("UseStandardSegmentNames") == "true"
        self.ui.outputSegmentationSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputSegmentation"))

        # Update buttons states and tooltips
        inputVolume = self._parameterNode.GetNodeReference("InputVolume")
        if inputVolume:
            self.ui.applyButton.toolTip = "Start segmentation"
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = "Select input volume"
            self.ui.applyButton.enabled = False

        if inputVolume:
            self.ui.outputSegmentationSelector.baseName = inputVolume.GetName() + " segmentation"

        fastModeSupported = self.logic.isFastModeSupportedForTask(task)
        self.ui.fastCheckBox.visible = fastModeSupported
        self.ui.fastNotAvailableLabel.visible = not fastModeSupported

        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

        self._parameterNode.SetNodeReferenceID("InputVolume", self.ui.inputVolumeSelector.currentNodeID)
        self._parameterNode.SetParameter("Task", self.ui.taskComboBox.currentData)
        self._parameterNode.SetParameter("Fast", "true" if self.ui.fastCheckBox.checked else "false")
        self._parameterNode.SetParameter("CPU", "true" if self.ui.cpuCheckBox.checked else "false")
        self._parameterNode.SetParameter("UseStandardSegmentNames", "true" if self.ui.useStandardSegmentNamesCheckBox.checked else "false")
        self._parameterNode.SetNodeReferenceID("OutputSegmentation", self.ui.outputSegmentationSelector.currentNodeID)

        self._parameterNode.EndModify(wasModified)

    def addLog(self, text):
        """Append text to log window
        """
        self.ui.statusLabel.appendPlainText(text)
        slicer.app.processEvents()  # force update

    def onApplyButton(self):
        """
        Run processing when user clicks "Apply" button.
        """
        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

            self.ui.statusLabel.plainText = ''
            self.logic.setupPythonRequirements()

            # Create new segmentation node, if not selected yet
            if not self.ui.outputSegmentationSelector.currentNode():
                self.ui.outputSegmentationSelector.addNode()

            self.logic.useStandardSegmentNames = self.ui.useStandardSegmentNamesCheckBox.checked

            # Compute output
            self.logic.process(self.ui.inputVolumeSelector.currentNode(), self.ui.outputSegmentationSelector.currentNode(),
                self.ui.fastCheckBox.checked, self.ui.cpuCheckBox.checked, self.ui.taskComboBox.currentData)

        self.ui.statusLabel.appendPlainText("\nProcessing finished.")

    def onPackageInfoUpdate(self):
        self.ui.packageInfoTextBrowser.plainText = ''
        with slicer.util.tryWithErrorDisplay("Failed to get TotalSegmentator package version information", waitCursor=True):
            self.ui.packageInfoTextBrowser.plainText = self.logic.installedTotalSegmentatorPythonPackageInfo().rstrip()

    def onPackageUpgrade(self):
        with slicer.util.tryWithErrorDisplay("Failed to upgrade TotalSegmentator", waitCursor=True):
            self.logic.setupPythonRequirements(upgrade=True)
        self.onPackageInfoUpdate()
        if not slicer.util.confirmOkCancelDisplay(f"This TotalSegmentator update requires a 3D Slicer restart.","Press OK to restart."):
            raise ValueError('Restart was cancelled.')
        else:
            slicer.util.restart()

    def onSetLicense(self):
        #import qt
        #filePath = qt.QFileDialog.getOpenFileName(None, 'Select TotalSegmentator weight file', '', "Zip file (*.zip)")
        if self.ui.licenseLineEdit.text:
            self.logic.setlicense(self.ui.licenseLineEdit.text)


#
# TotalSegmentatorLogic
#

class TotalSegmentatorLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        from collections import OrderedDict

        ScriptedLoadableModuleLogic.__init__(self)

        self.totalSegmentatorPythonPackageDownloadUrl = "https://github.com/wasserth/TotalSegmentator/archive/bbc1e7b3df64339e67acbebe2cf3c739098aabf4.zip"  # tag: 2.0.5

        self.logCallback = None
        self.clearOutputFolder = True
        self.useStandardSegmentNames = True
        self.pullMaster = False
        self.totalSegmentatorLabelTerminology = {}  # Map from TotalSegmentator structure name to terminology string

        self.tasks = OrderedDict()
        self.tasks['total'] = {'label': 'total', 'supportsFast': True, 'supportsMultiLabel': True}
        self.tasks['lung_vessels'] = {'label': 'lung vessels', 'requiresPreSegmentation': True}
        self.tasks['cerebral_bleed'] = {'label': 'cerebral bleed', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['hip_implant'] = {'label': 'hip implant', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['coronary_arteries'] = {'label': 'coronary arteries', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['body'] = {'label': 'body', 'supportsFast': True}
        self.tasks['pleural_pericard_effusion'] = {'label': 'pleural and pericardial effusion', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['covid'] = {'label': 'covid', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['liver_vessels'] = {'label': 'liver vessels', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['appendicular_bones'] = {'label': 'appendicular_bones', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['tissue_types'] = {'label': 'tissue types', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['heartchambers_highres'] = {'label': 'heartchambers highres' ,  'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['head'] = {'label': 'head', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['face'] = {'label': 'face', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['aortic_branches'] = {'label': 'aortic branches', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['heartchambers_test'] = {'label': 'heartchambers test', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['aortic_branches_test'] = {'label': 'aortic branches test', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['bones_tissue_test'] = {'label': 'bones tissue test', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['test'] = {'label': 'test', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}


        # self.tasks['covid'] = {'label': 'pleural and pericardial effusion'}

        self.loadTotalSegmentatorLabelTerminology()

    def loadTotalSegmentatorLabelTerminology(self):
        """Load label terminology from totalsegmentator_snomed_mapping.csv file.
        Terminology entries are either in DICOM or TotalSegmentator "Segmentation category and type".
        """

        moduleDir = os.path.dirname(slicer.util.getModule('TotalSegmentator').path)
        totalSegmentatorTerminologyMappingFilePath = os.path.join(moduleDir, 'Resources', 'totalsegmentator_snomed_mapping.csv')

        terminologiesLogic = slicer.util.getModuleLogic('Terminologies')
        totalSegmentatorTerminologyName = "Segmentation category and type - Total Segmentator"

        anatomicalStructureCategory = slicer.vtkSlicerTerminologyCategory()
        numberOfCategories = terminologiesLogic.GetNumberOfCategoriesInTerminology(totalSegmentatorTerminologyName)
        for i in range(numberOfCategories):
            terminologiesLogic.GetNthCategoryInTerminology(totalSegmentatorTerminologyName, i, anatomicalStructureCategory)
            if anatomicalStructureCategory.GetCodingSchemeDesignator() == 'SCT' and anatomicalStructureCategory.GetCodeValue() == '123037004':
                # Found the (123037004, SCT, "Anatomical Structure") category within DICOM master list
                break

        self.totalSegmentatorAnatomicalStuctures = []  # List of codes that are specified by in the TotalSegmentator terminology (SCT^123456)
        terminologyType = slicer.vtkSlicerTerminologyType()
        numberOfTypes = terminologiesLogic.GetNumberOfTypesInTerminologyCategory(totalSegmentatorTerminologyName, anatomicalStructureCategory)
        for i in range(numberOfTypes):
            if terminologiesLogic.GetNthTypeInTerminologyCategory(totalSegmentatorTerminologyName, anatomicalStructureCategory, i, terminologyType):
                self.totalSegmentatorAnatomicalStuctures.append(terminologyType.GetCodingSchemeDesignator() + "^" + terminologyType.GetCodeValue())

        # Helper function to get code string from CSV file row
        def getCodeString(field, columnNames, row):
            columnValues = []
            for fieldName in ["CodingSchemeDesignator", "CodeValue", "CodeMeaning"]:
                columnIndex = columnNames.index(f"{field}.{fieldName}")
                try:
                    columnValue = row[columnIndex]
                except IndexError:
                    # Probably the line in the CSV file was not terminated by multiple commas (,)
                    columnValue = ''
                columnValues.append(columnValue)
            return columnValues

        import csv
        with open(totalSegmentatorTerminologyMappingFilePath, "r") as f:
            reader = csv.reader(f)
            columnNames = next(reader)
            data = {}
            # Loop through the rows of the csv file
            for row in reader:

                # Determine segmentation category (DICOM or TotalSegmentator)
                terminologyEntryStrWithoutCategoryName = (
                    "~"
                    + '^'.join(getCodeString("SegmentedPropertyCategoryCodeSequence", columnNames, row))  # SCT^123037004^Anatomical Structure
                    + '~'
                    + '^'.join(getCodeString("SegmentedPropertyTypeCodeSequence", columnNames, row))  # SCT^23451007^Adrenal gland
                    + '~'
                    + '^'.join(getCodeString("SegmentedPropertyTypeModifierCodeSequence", columnNames, row))  # SCT^7771000^Left
                    + '~Anatomic codes - DICOM master list~^^~^^|')
                terminologyEntry = slicer.vtkSlicerTerminologyEntry()
                anatomicalStructureCodeStr = (  # Example: SCT^23451007
                    row[columnNames.index("SegmentedPropertyTypeCodeSequence.CodingSchemeDesignator")]
                    + "^" + row[columnNames.index("SegmentedPropertyTypeCodeSequence.CodeValue")])
                if anatomicalStructureCodeStr in self.totalSegmentatorAnatomicalStuctures:
                    terminologyEntryStr = "Segmentation category and type - Total Segmentator" + terminologyEntryStrWithoutCategoryName
                else:
                    terminologyEntryStr = "Segmentation category and type - DICOM master list" + terminologyEntryStrWithoutCategoryName

                # Store the terminology string for this structure
                totalSegmentatorStructureName = row[columnNames.index("Structure")]  # TotalSegmentator structure name, such as "adrenal_gland_left"
                self.totalSegmentatorLabelTerminology[totalSegmentatorStructureName] = terminologyEntryStr


    def isFastModeSupportedForTask(self, task):
        return (task in self.tasks) and ('supportsFast' in self.tasks[task]) and self.tasks[task]['supportsFast']

    def isMultiLabelSupportedForTask(self, task):
        return (task in self.tasks) and ('supportsMultiLabel' in self.tasks[task]) and self.tasks[task]['supportsMultiLabel']

    def isPreSegmentationRequiredForTask(self, task):
        return (task in self.tasks) and ('requiresPreSegmentation' in self.tasks[task]) and self.tasks[task]['requiresPreSegmentation']

    def getSegmentLabelColor(self, terminologyEntryStr):
        """Get segment label and color from terminology"""

        def labelColorFromTypeObject(typeObject):
            """typeObject is a terminology type or type modifier"""
            label = typeObject.GetSlicerLabel() if typeObject.GetSlicerLabel() else typeObject.GetCodeMeaning()
            rgb = typeObject.GetRecommendedDisplayRGBValue()
            return label, (rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)

        tlogic = slicer.modules.terminologies.logic()

        terminologyEntry = slicer.vtkSlicerTerminologyEntry()
        if not tlogic.DeserializeTerminologyEntry(terminologyEntryStr, terminologyEntry):
            raise RuntimeError(f"Failed to deserialize terminology string: {terminologyEntryStr}")

        numberOfTypes = tlogic.GetNumberOfTypesInTerminologyCategory(terminologyEntry.GetTerminologyContextName(), terminologyEntry.GetCategoryObject())
        foundTerminologyEntry = slicer.vtkSlicerTerminologyEntry()
        for typeIndex in range(numberOfTypes):
            tlogic.GetNthTypeInTerminologyCategory(terminologyEntry.GetTerminologyContextName(), terminologyEntry.GetCategoryObject(), typeIndex, foundTerminologyEntry.GetTypeObject())
            if terminologyEntry.GetTypeObject().GetCodingSchemeDesignator() != foundTerminologyEntry.GetTypeObject().GetCodingSchemeDesignator():
                continue
            if terminologyEntry.GetTypeObject().GetCodeValue() != foundTerminologyEntry.GetTypeObject().GetCodeValue():
                continue
            if terminologyEntry.GetTypeModifierObject() and terminologyEntry.GetTypeModifierObject().GetCodeValue():
                # Type has a modifier, get the color from there
                numberOfModifiers = tlogic.GetNumberOfTypeModifiersInTerminologyType(terminologyEntry.GetTerminologyContextName(), terminologyEntry.GetCategoryObject(), terminologyEntry.GetTypeObject())
                foundMatchingModifier = False
                for modifierIndex in range(numberOfModifiers):
                    tlogic.GetNthTypeModifierInTerminologyType(terminologyEntry.GetTerminologyContextName(), terminologyEntry.GetCategoryObject(), terminologyEntry.GetTypeObject(),
                        modifierIndex, foundTerminologyEntry.GetTypeModifierObject())
                    if terminologyEntry.GetTypeModifierObject().GetCodingSchemeDesignator() != foundTerminologyEntry.GetTypeModifierObject().GetCodingSchemeDesignator():
                        continue
                    if terminologyEntry.GetTypeModifierObject().GetCodeValue() != foundTerminologyEntry.GetTypeModifierObject().GetCodeValue():
                        continue
                    return labelColorFromTypeObject(foundTerminologyEntry.GetTypeModifierObject())
                continue
            return labelColorFromTypeObject(foundTerminologyEntry.GetTypeObject())

        raise RuntimeError(f"Color was not found for terminology {terminologyEntryStr}")

    def log(self, text):
        logging.info(text)
        if self.logCallback:
            self.logCallback(text)

    def installedTotalSegmentatorPythonPackageDownloadUrl(self):
        """Get package download URL of the installed TotalSegmentator Python package"""
        import importlib.metadata
        import json
        try:
            metadataPath = [p for p in importlib.metadata.files('TotalSegmentator') if 'direct_url.json' in str(p)][0]
            with open(metadataPath.locate()) as json_file:
                data = json.load(json_file)
            return data['url']
        except:
            # Failed to get version information, probably not installed from download URL
            return None

    def installedTotalSegmentatorPythonPackageInfo(self):
        import shutil
        import subprocess
        versionInfo = subprocess.check_output([shutil.which('PythonSlicer'), "-m", "pip", "show", "TotalSegmentator"]).decode()

        # Get download URL, as the version information does not contain the github hash
        downloadUrl = self.installedTotalSegmentatorPythonPackageDownloadUrl()
        if downloadUrl:
            versionInfo += "Download URL: " + downloadUrl

        return versionInfo

    def simpleITKPythonPackageVersion(self):
        """Utility function to get version of currently installed SimpleITK.
        Currently not used, but it can be useful for diagnostic purposes.
        """

        import shutil
        import subprocess
        versionInfo = subprocess.check_output([shutil.which('PythonSlicer'), "-m", "pip", "show", "SimpleITK"]).decode()

        # versionInfo looks something like this:
        #
        #   Name: SimpleITK
        #   Version: 2.2.0rc2.dev368
        #   Summary: SimpleITK is a simplified interface to the Insight Toolkit (ITK) for image registration and segmentation
        #   ...
        #

        # Get version string (second half of the second line):
        version = versionInfo.split('\n')[1].split(' ')[1].strip()
        return version

    def pipInstallSelective(self, packageToInstall, installCommand, packagesToSkip):
        """Installs a Python package, skipping a list of packages.
        Return the list of skipped requirements (package name with version requirement).
        """
        slicer.util.pip_install(f"{installCommand} --no-deps")
        skippedRequirements = []  # list of all missed packages and their version

        # Get path to site-packages\nnunetv2-2.2.dist-info\METADATA
        import importlib.metadata
        metadataPath = [p for p in importlib.metadata.files(packageToInstall) if 'METADATA' in str(p)][0]
        metadataPath.locate()

        # Remove line: `Requires-Dist: SimpleITK (==2.0.2)`
        filteredMetadata = ""
        with open(metadataPath.locate(), "r+") as file:
            for line in file:
                skipThisPackage = False
                requirementPrefix = 'Requires-Dist: '
                if line.startswith(requirementPrefix):
                    for packageToSkip in packagesToSkip:
                        if packageToSkip in line:
                            skipThisPackage = True
                            break
                if skipThisPackage:
                    # skip SimpleITK requirement
                    skippedRequirements.append(line.removeprefix(requirementPrefix))
                    continue
                filteredMetadata += line
            # Update file content with filtered result
            file.seek(0)
            file.write(filteredMetadata)
            file.truncate()

        # Install all dependencies but the ones listed in packagesToSkip
        import importlib.metadata
        requirements = importlib.metadata.requires(packageToInstall)
        for requirement in requirements:
            skipThisPackage = False
            for packageToSkip in packagesToSkip:
                if requirement.startswith(packageToSkip):
                    # Do not install
                    skipThisPackage = True
                    break

            match = False
            if not match:
                # ruff ; extra == 'dev' -> rewrite to: ruff[extra]
                match = re.match(r"([\S]+)[\s]*; extra == '([^']+)'", requirement)
                if match:
                    requirement = f"{match.group(1)}[{match.group(2)}]"
            if not match:
                # nibabel >=2.3.0 -> rewrite to: nibabel>=2.3.0
                match = re.match("([\S]+)[\s](.+)", requirement)
                if match:
                    requirement = f"{match.group(1)}{match.group(2)}"

            if skipThisPackage:
                self.log(f'- Skip {requirement}')
            else:
                self.log(f'- Installing {requirement}...')
                slicer.util.pip_install(requirement)

        return skippedRequirements

    def setupPythonRequirements(self, upgrade=False):

        import importlib.util

        # These packages come preinstalled with Slicer and should remain unchanged
        packagesToSkip = [
            'SimpleITK',  # Slicer's SimpleITK uses a special IO class, which should not be replaced
            'torch',  # needs special installation using SlicerPyTorch
            'requests',  # TotalSegmentator would want to force a specific version of requests, which would require a restart of Slicer and it is unnecessary
            ]

        # Install PyTorch
        try:
          import PyTorchUtils
        except ModuleNotFoundError as e:
          raise RuntimeError("This module requires PyTorch extension. Install it from the Extensions Manager.")

        minimumTorchVersion = "1.12"
        torchLogic = PyTorchUtils.PyTorchUtilsLogic()
        if not torchLogic.torchInstalled():
            self.log('PyTorch Python package is required. Installing... (it may take several minutes)')
            torch = torchLogic.installTorch(askConfirmation=True, torchVersionRequirement = f">={minimumTorchVersion}")
            if torch is None:
                raise ValueError('PyTorch extension needs to be installed to use this module.')
        else:
            # torch is installed, check version
            from packaging import version
            if version.parse(torchLogic.torch.__version__) < version.parse(minimumTorchVersion):
                raise ValueError(f'PyTorch version {torchLogic.torch.__version__} is not compatible with this module.'
                                 + f' Minimum required version is {minimumTorchVersion}. You can use "PyTorch Util" module to install PyTorch'
                                 + f' with version requirement set to: >={minimumTorchVersion}')

        # Install TotalSegmentator with selected dependencies only
        # (it would replace Slicer's "requests")
        needToInstallSegmenter = False
        try:
            import totalsegmentator
            if not upgrade:
                # Check if we need to update TotalSegmentator Python package version
                downloadUrl = self.installedTotalSegmentatorPythonPackageDownloadUrl()
                if downloadUrl and (downloadUrl != self.totalSegmentatorPythonPackageDownloadUrl):
                    # TotalSegmentator have been already installed from GitHub, from a different URL that this module needs
                    if not slicer.util.confirmOkCancelDisplay(
                        f"This module requires TotalSegmentator Python package update.",
                        detailedText=f"Currently installed: {downloadUrl}\n\nRequired: {self.totalSegmentatorPythonPackageDownloadUrl}"):
                      raise ValueError('TotalSegmentator update was cancelled.')
                    upgrade = True
        except ModuleNotFoundError as e:
            needToInstallSegmenter = True

        if needToInstallSegmenter or upgrade:
            self.log(f'TotalSegmentator Python package is required. Installing it from {self.totalSegmentatorPythonPackageDownloadUrl}... (it may take several minutes)')

            if upgrade:
                # TotalSegmentator version information is usually not updated with each git revision, therefore we must uninstall it to force the upgrade
                slicer.util.pip_uninstall("TotalSegmentator")

            # Update TotalSegmentator and all its dependencies
            skippedRequirements = self.pipInstallSelective(
                "TotalSegmentator",
                self.totalSegmentatorPythonPackageDownloadUrl + (" --upgrade" if upgrade else ""),
                packagesToSkip + ["nnunetv2"])

            # Install nnunetv2 with selected dependencies only
            # (it would replace Slicer's "SimpleITK")
            try:
                nnunetRequirement = next(requirement for requirement in skippedRequirements if requirement.startswith('nnunetv2'))
            except StopIteration:
                # nnunetv2 requiremen was not found in TotalSegmentator - this must be an error, so let's report it
                raise ValueError("nnunetv2 requiremen was not found in TotalSegmentator")
            # Remove spaces and parentheses from version requirement (convert from "nnunetv2 (==2.1)" to "nnunetv2==2.1")
            import re
            nnunetRequirement = re.sub('[ \(\)]', '', nnunetRequirement)
            self.log(f'nnunetv2 Python package is required. Installing {nnunetRequirement} ...')
            self.pipInstallSelective('nnunetv2', nnunetRequirement, packagesToSkip)

            self.log('TotalSegmentator installation is completed successfully.')


    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        if not parameterNode.GetParameter("Fast"):
            parameterNode.SetParameter("Fast", "True")
        if not parameterNode.GetParameter("Task"):
            parameterNode.SetParameter("Task", "total")
        if not parameterNode.GetParameter("UseStandardSegmentNames"):
            parameterNode.SetParameter("UseStandardSegmentNames", "true")

    def logProcessOutput(self, proc):
        # Wait for the process to end and forward output to the log
        from subprocess import CalledProcessError
        while True:
            try:
                line = proc.stdout.readline()
            except UnicodeDecodeError as e:
                # Code page conversion happens because `universal_newlines=True` sets process output to text mode,
                # and it fails because probably system locale is not UTF8. We just ignore the error and discard the string,
                # as we only guarantee correct behavior if an UTF8 locale is used.
                pass
            if not line:
                break
            self.log(line.rstrip())
        proc.wait()
        retcode = proc.returncode
        if retcode != 0:
            raise CalledProcessError(retcode, proc.args, output=proc.stdout, stderr=proc.stderr)


    def check_zip_extension(self, file_path):
        _, ext = os.path.splitext(file_path)

        if ext.lower() != '.zip':
            raise ValueError(f"The selected file '{file_path}' is not a .zip file!")

    @staticmethod
    def executableName(name):
        return name + ".exe" if os.name == "nt" else name

    def setlicense(self, licenseStr):

        """
        Import weights.
        Weights are provided in ZIP format.
        This function can be used without GUI widget.
        """

        # Get totalseg_import_weights command
        # totalseg_import_weights (.py file, without extension) is installed in Python Scripts folder

        if not licenseStr:
            raise ValueError(f"The license string is empty.")

        self.log('Set license started ...')
        import sysconfig

        totalseg_set_license_Path = os.path.join(sysconfig.get_path('scripts'), TotalSegmentatorLogic.executableName("totalseg_set_license"))
        # Get Python executable path
        import shutil
        pythonSlicerExecutablePath = shutil.which('PythonSlicer')
        if not pythonSlicerExecutablePath:
            raise RuntimeError("Python was not found")
        totalseg_set_license_Command = [ pythonSlicerExecutablePath, totalseg_set_license_Path]
        options = ["-l", licenseStr]

        # Launch command
        cmd = totalseg_set_license_Command + options
        # print(*cmd)
        proc = slicer.util.launchConsoleProcess(cmd)
        self.logProcessOutput(proc)
        self.log('Set license finished.')

        if not slicer.util.confirmOkCancelDisplay(f"This license update requires a 3D Slicer restart.","Press OK to restart."):
            raise ValueError('Restart was cancelled.')
        else:
            slicer.util.restart()


    def process(self, inputVolume, outputSegmentation, fast=True, cpu=False, task=None, subset=None):

        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param inputVolume: volume to be thresholded
        :param outputVolume: thresholding result
        :param fast: faster and less accurate output
        :param task: one of self.tasks, default is "total"
        :param subset: a list of structures (TotalSegmentator classe names https://github.com/wasserth/TotalSegmentator#class-detailsTotalSegmentator) to segment.
          Default is None, which means that all available structures will be segmented."
        """

        if not inputVolume:
            raise ValueError("Input or output volume is invalid")

        if task == None and not subset:
            task = "total"

        import time
        startTime = time.time()
        self.log('Processing started')

        import sysconfig

        print(sysconfig.get_path('scripts'))
        os.environ["TOTALSEG_WEIGHTS_PATH"] = sysconfig.get_path('scripts')

        # Create new empty folder
        tempFolder = slicer.util.tempDirectory()

        inputFile = tempFolder+"/total-segmentator-input.nii"
        outputSegmentationFolder = tempFolder + "/segmentation"
        # print (outputSegmentationFolder)
        outputSegmentationFile = tempFolder + "/segmentation.nii"

        # Recommend the user to switch to fast mode if no GPU or not enough memory is available
        import torch

        cuda = torch.cuda if torch.has_cuda and torch.cuda.is_available() else None

        if not fast and not cuda:

            import ctk
            import qt
            mbox = ctk.ctkMessageBox(slicer.util.mainWindow())
            mbox.text = "No GPU is detected. Switch to 'fast' mode to get low-resolution result in a few minutes or compute full-resolution result in about an hour?"
            mbox.addButton("Fast (~2 minutes)", qt.QMessageBox.AcceptRole)
            mbox.addButton("Full-resolution (~50 minutes)", qt.QMessageBox.RejectRole)
            # Windows 10 peek feature in taskbar shows all hidden but not destroyed windows
            # (after creating and closing a messagebox, hovering over the mouse on Slicer icon, moving up the
            # mouse to the peek thumbnail would show it again).
            mbox.deleteLater()
            fast = (mbox.exec_() == qt.QMessageBox.AcceptRole)

        if not fast and cuda and cuda.get_device_properties(cuda.current_device()).total_memory < 7e9:
            if slicer.util.confirmYesNoDisplay("You have less than 7 GB of GPU memory available. Enable 'fast' mode to ensure segmentation can be completed successfully?"):
                fast = True

        # Get TotalSegmentator launcher command
        # TotalSegmentator (.py file, without extension) is installed in Python Scripts folder
        import sysconfig
        totalSegmentatorPath = os.path.join(sysconfig.get_path('scripts'), TotalSegmentatorLogic.executableName("TotalSegmentator"))
        # Get Python executable path
        import shutil
        pythonSlicerExecutablePath = shutil.which('PythonSlicer')
        if not pythonSlicerExecutablePath:
            raise RuntimeError("Python was not found")
        totalSegmentatorCommand = [ pythonSlicerExecutablePath, totalSegmentatorPath]

        # Write input volume to file
        # TotalSegmentator requires NIFTI
        self.log(f"Writing input file to {inputFile}")
        volumeStorageNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLVolumeArchetypeStorageNode")
        volumeStorageNode.SetFileName(inputFile)
        volumeStorageNode.UseCompressionOff()
        volumeStorageNode.WriteData(inputVolume)
        volumeStorageNode.UnRegister(None)

        # Get options
        options = ["-i", inputFile, "-o", outputSegmentationFolder]

        # Launch TotalSegmentator in fast mode to get initial segmentation, if needed

        #options.extend(["--nr_thr_saving", "1"])
        #options.append("--force_split")

        if self.isPreSegmentationRequiredForTask(task):
            preOptions = options + ["--fast"]
            self.log('Creating segmentations with TotalSegmentator AI (pre-run)...')
            self.log(f"Total Segmentator arguments: {preOptions}")
            proc = slicer.util.launchConsoleProcess(totalSegmentatorCommand + preOptions)
            self.logProcessOutput(proc)

        # Launch TotalSegmentator

        # When there are many segments then reading each segment from a separate file would be too slow,
        # but we need to do it for some specialized models.
        multilabel = self.isMultiLabelSupportedForTask(task)

        # some tasks do not support fast mode
        if not self.isFastModeSupportedForTask(task):
            fast = False

        if multilabel:
            options.append("--ml")
        if task:
            options.extend(["--task", task])
        if fast:
            options.append("--fast")
        if cpu:
            options.extend(["--device", "cpu"])
        if subset:
            options.append("--roi_subset")
            # append each item of the subset
            for item in subset:
                try:
                    if self.totalSegmentatorLabelTerminology[item]:
                        options.append(item)
                except:
                    # Failed to get terminology info, item probably misspelled
                    raise ValueError("'" + item + "' is not a valid TotalSegmentator label terminology.")

        self.log('Creating segmentations with TotalSegmentator AI...')
        self.log(f"Total Segmentator arguments: {options}")
        proc = slicer.util.launchConsoleProcess(totalSegmentatorCommand + options)
        self.logProcessOutput(proc)

        # Load result
        self.log('Importing segmentation results...')
        if multilabel:
            self.readSegmentation(outputSegmentation, outputSegmentationFile, task)
        else:
            self.readSegmentationFolder(outputSegmentation, outputSegmentationFolder, task, subset)

        # Set source volume - required for DICOM Segmentation export
        outputSegmentation.SetNodeReferenceID(outputSegmentation.GetReferenceImageGeometryReferenceRole(), inputVolume.GetID())
        outputSegmentation.SetReferenceImageGeometryParameterFromVolumeNode(inputVolume)

        # Place segmentation node in the same place as the input volume
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        inputVolumeShItem = shNode.GetItemByDataNode(inputVolume)
        studyShItem = shNode.GetItemParent(inputVolumeShItem)
        segmentationShItem = shNode.GetItemByDataNode(outputSegmentation)
        shNode.SetItemParent(segmentationShItem, studyShItem)

        if self.clearOutputFolder:
            self.log("Cleaning up temporary folder...")
            if os.path.isdir(tempFolder):
                shutil.rmtree(tempFolder)
        else:
            self.log(f"Not cleaning up temporary folder: {tempFolder}")

        stopTime = time.time()
        self.log(f'Processing completed in {stopTime-startTime:.2f} seconds')

    def readSegmentationFolder(self, outputSegmentation, output_segmentation_dir, task, subset=None):
        """
        The method is very slow, but this is the only option for some specialized tasks.
        """

        import os

        outputSegmentation.GetSegmentation().RemoveAllSegments()

        # Get color node with random colors
        randomColorsNode = slicer.mrmlScene.GetNodeByID('vtkMRMLColorTableNodeRandom')
        rgba = [0, 0, 0, 0]
        # Get label descriptions

        from totalsegmentator.map_to_binary import class_map
        # Get label descriptions if task is provided
        labelValueToSegmentName = class_map[task] if task else {}

        def import_labelmap_to_segmentation(labelmapVolumeNode, segmentName, segmentId):
            updatedSegmentIds = vtk.vtkStringArray()
            updatedSegmentIds.InsertNextValue(segmentId)
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelmapVolumeNode, outputSegmentation, updatedSegmentIds)
            self.setTerminology(outputSegmentation, segmentName, segmentId)
            slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

        # Read each candidate file
        for labelValue, segmentName in labelValueToSegmentName.items():
            self.log(f"Importing candidate {segmentName}")
            labelVolumePath = os.path.join(output_segmentation_dir, f"{segmentName}.nii.gz")
            if not os.path.exists(labelVolumePath):
                self.log(f"Path {segmentName} not exists.")
                continue
            labelmapVolumeNode = slicer.util.loadLabelVolume(labelVolumePath, {"name": segmentName})
            randomColorsNode.GetColor(labelValue, rgba)
            segmentId = outputSegmentation.GetSegmentation().AddEmptySegment(segmentName, segmentName, rgba[0:3])
            import_labelmap_to_segmentation(labelmapVolumeNode, segmentName, segmentId)

        # Read each subset file if subset is provided
        if subset is not None and task is None:
            for segmentName in subset:
                self.log(f"Importing subset {segmentName}")
                labelVolumePath = os.path.join(output_segmentation_dir, f"{segmentName}.nii.gz")
                if os.path.exists(labelVolumePath):
                    labelmapVolumeNode = slicer.util.loadLabelVolume(labelVolumePath, {"name": segmentName})
                    segmentId = outputSegmentation.GetSegmentation().AddEmptySegment(segmentName, segmentName)
                    import_labelmap_to_segmentation(labelmapVolumeNode, segmentName, segmentId)
                else:
                    self.log(f"{segmentName} not found.")

    def readSegmentation(self, outputSegmentation, outputSegmentationFile, task):

        # Get label descriptions
        from totalsegmentator.map_to_binary import class_map
        labelValueToSegmentName = class_map[task]
        maxLabelValue = max(labelValueToSegmentName.keys())
        if min(labelValueToSegmentName.keys()) < 0:
            raise RuntimeError("Label values in class_map must be positive")

        # Get color node with random colors
        randomColorsNode = slicer.mrmlScene.GetNodeByID('vtkMRMLColorTableNodeRandom')
        rgba = [0, 0, 0, 0]

        # Create color table for this segmentation task
        colorTableNode = slicer.vtkMRMLColorTableNode()
        colorTableNode.SetTypeToUser()
        colorTableNode.SetNumberOfColors(maxLabelValue+1)
        colorTableNode.SetName(task)
        for labelValue in labelValueToSegmentName:
            randomColorsNode.GetColor(labelValue,rgba)
            colorTableNode.SetColor(labelValue, rgba[0], rgba[1], rgba[2], rgba[3])
            colorTableNode.SetColorName(labelValue, labelValueToSegmentName[labelValue])
        slicer.mrmlScene.AddNode(colorTableNode)

        # Load the segmentation
        outputSegmentation.SetLabelmapConversionColorTableNodeID(colorTableNode.GetID())
        outputSegmentation.AddDefaultStorageNode()
        storageNode = outputSegmentation.GetStorageNode()
        storageNode.SetFileName(outputSegmentationFile)
        storageNode.ReadData(outputSegmentation)

        slicer.mrmlScene.RemoveNode(colorTableNode)

        # Set terminology and color
        for labelValue in labelValueToSegmentName:
            segmentName = labelValueToSegmentName[labelValue]
            segmentId = segmentName
            self.setTerminology(outputSegmentation, segmentName, segmentId)

    def setTerminology(self, segmentation, segmentName, segmentId):
        segment = segmentation.GetSegmentation().GetSegment(segmentId)
        if not segment:
            # Segment is not present in this segmentation
            return
        if segmentName in self.totalSegmentatorLabelTerminology:
            terminologyEntryStr = self.totalSegmentatorLabelTerminology[segmentName]
            segment.SetTag(segment.GetTerminologyEntryTagName(), terminologyEntryStr)
            try:
                label, color = self.getSegmentLabelColor(terminologyEntryStr)
                if self.useStandardSegmentNames:
                    segment.SetName(label)
                segment.SetColor(color)
            except RuntimeError as e:
                self.log(str(e))

#
# TotalSegmentatorTest
#

class TotalSegmentatorTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_TotalSegmentator1()
        self.setUp()
        self.test_TotalSegmentatorSubset()

    def test_TotalSegmentator1(self):
        """ Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        import SampleData
        inputVolume = SampleData.downloadSample('CTACardio')
        self.delayDisplay('Loaded test data set')

        outputSegmentation = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentationNode')

        # Test the module logic

        # Logic testing is disabled by default to not overload automatic build machines (pytorch is a huge package and computation
        # on CPU takes 5-10 minutes). Set testLogic to True to enable testing.
        testLogic = False

        if testLogic:
            logic = TotalSegmentatorLogic()
            logic.logCallback = self._mylog

            self.delayDisplay('Set up required Python packages')
            logic.setupPythonRequirements()

            self.delayDisplay('Compute output')
            logic.process(inputVolume, outputSegmentation, fast=False)

        else:
            logging.warning("test_TotalSegmentator1 logic testing was skipped")

        self.delayDisplay('Test passed')

    def _mylog(self,text):
        print(text)

    def test_TotalSegmentatorSubset(self):
        """ Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        import SampleData
        inputVolume = SampleData.downloadSample('CTACardio')
        self.delayDisplay('Loaded test data set')

        outputSegmentation = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentationNode')

        # Test the module logic

        # Logic testing is disabled by default to not overload automatic build machines (pytorch is a huge package and computation
        # on CPU takes 5-10 minutes). Set testLogic to True to enable testing.
        testLogic = False

        if testLogic:
            logic = TotalSegmentatorLogic()
            logic.logCallback = self._mylog

            self.delayDisplay('Set up required Python packages')
            logic.setupPythonRequirements()

            self.delayDisplay('Compute output')
            _subset = ["lung_upper_lobe_left","lung_lower_lobe_right","trachea"]
            logic.process(inputVolume, outputSegmentation, fast = False, subset = _subset)

        else:
            logging.warning("test_TotalSegmentator1 logic testing was skipped")

        self.delayDisplay('Test passed')