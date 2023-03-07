import logging
import os

import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin


#
# TotalSegmentator
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
        self.ui.useStandardSegmentNamesCheckBox.connect('toggled(bool)', self.updateParameterNodeFromGUI)
        self.ui.taskComboBox.currentTextChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.outputSegmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.outputSegmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.ui.segmentationShow3DButton.setSegmentationNode)

        # Buttons
        self.ui.packageInfoUpdateButton.connect('clicked(bool)', self.onPackageInfoUpdate)
        self.ui.packageUpgradeButton.connect('clicked(bool)', self.onPackageUpgrade)
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
                self.ui.fastCheckBox.checked, self.ui.taskComboBox.currentData)

        self.ui.statusLabel.appendPlainText("\nProcessing finished.")

    def onPackageInfoUpdate(self):
        self.ui.packageInfoTextBrowser.plainText = ''
        with slicer.util.tryWithErrorDisplay("Failed to get TotalSegmenter package version information", waitCursor=True):
            self.ui.packageInfoTextBrowser.plainText = self.logic.installedTotalSegmentatorPythonPackageInfo().rstrip()

    def onPackageUpgrade(self):
        with slicer.util.tryWithErrorDisplay("Failed to upgrade TotalSegmenter", waitCursor=True):
            self.logic.setupPythonRequirements(upgrade=True)
        self.onPackageInfoUpdate()

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

        self.totalSegmentatorPythonPackageDownloadUrl = "https://github.com/wasserth/TotalSegmentator/archive/ecf84f9e59b84dddb447e2b13542f58c29ee4c6a.zip"

        self.logCallback = None
        self.clearOutputFolder = True
        self.useStandardSegmentNames = True

        self.tasks = OrderedDict()
        self.tasks['total'] = {'label': 'total', 'supportsFast': True, 'supportsMultiLabel': True}
        self.tasks['lung_vessels'] = {'label': 'lung vessels', 'requiresPreSegmentation': True}
        self.tasks['cerebral_bleed'] = {'label': 'cerebral bleed', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['hip_implant'] = {'label': 'hip implant', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['coronary_arteries'] = {'label': 'coronary arteries', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        self.tasks['body'] = {'label': 'body', 'supportsFast': True}
        self.tasks['pleural_pericard_effusion'] = {'label': 'pleural and pericardial effusion', 'requiresPreSegmentation': True, 'supportsMultiLabel': True}
        # self.tasks['covid'] = {'label': 'pleural and pericardial effusion'}

        self.totalSegmentatorLabelTerminology = {
            "spleen": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^78961009^Spleen~^^~Anatomic codes - DICOM master list~^^~^^|",
            "kidney_right": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^64033007^Kidney~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "kidney_left": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^64033007^Kidney~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "gallbladder": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^28231008^Gallbladder~^^~Anatomic codes - DICOM master list~^^~^^|",
            "liver": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^10200004^Liver~^^~Anatomic codes - DICOM master list~^^~^^|",
            "stomach": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^69695003^Stomach~^^~Anatomic codes - DICOM master list~^^~^^|",
            "aorta": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^15825003^Aorta~^^~Anatomic codes - DICOM master list~^^~^^|",
            "inferior_vena_cava": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^64131007^Inferior vena cava~^^~Anatomic codes - DICOM master list~^^~^^|",
            "portal_vein_and_splenic_vein": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^32764006^Portal vein~^^~Anatomic codes - DICOM master list~^^~^^|",
            "pancreas": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^15776009^Pancreas~^^~Anatomic codes - DICOM master list~^^~^^|",
            "adrenal_gland_right": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^23451007^Adrenal gland~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "adrenal_gland_left": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^23451007^Adrenal gland~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "lung_upper_lobe_left": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^45653009^Upper lobe of lung~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "lung_lower_lobe_left": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^90572001^Lower lobe of lung~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "lung_upper_lobe_right": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^45653009^Upper lobe of lung~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "lung_middle_lobe_right": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^72481006^Middle lobe of right lung~^^~Anatomic codes - DICOM master list~^^~^^|",
            "lung_lower_lobe_right": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^90572001^Lower lobe of lung~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_L5": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^49668003^L5 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_L4": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^11994002^L4 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_L3": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^36470004^L3 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_L2": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^14293000^L2 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_L1": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^66794005^L1 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_T12": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^23215003^T12 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_T11": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^12989004^T11 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_T10": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^7610001^T10 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_T9": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^82687006^T9 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_T8": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^11068009^T8 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_T7": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^62487009^T7 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_T6": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^45296009^T6 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_T5": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^56401006^T5 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_T4": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^73071006^T4 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_T3": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^1626008^T3 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_T2": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^53733008^T2 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_T1": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^64864005^T1 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_C7": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^87391001^C7 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_C6": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^36054005^C6 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_C5": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^36978003^C5 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_C4": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^5329002^C4 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_C3": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^113205007^C3 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_C2": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^39976000^C2 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "vertebrae_C1": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^14806007^C1 vertebra~^^~Anatomic codes - DICOM master list~^^~^^|",
            "esophagus": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^32849002^Esophagus~^^~Anatomic codes - DICOM master list~^^~^^|",
            "trachea": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^44567001^Trachea~^^~Anatomic codes - DICOM master list~^^~^^|",
            "heart_myocardium": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^80891009^Heart~^^~Anatomic codes - DICOM master list~^^~^^|",
            "heart_atrium_left": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^82471001^Left atrium~^^~Anatomic codes - DICOM master list~^^~^^|",
            "heart_ventricle_left": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^87878005^Left ventricle~^^~Anatomic codes - DICOM master list~^^~^^|",
            "heart_atrium_right": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^73829009^Right atrium~^^~Anatomic codes - DICOM master list~^^~^^|",
            "heart_ventricle_right": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^53085002^Right ventricle~^^~Anatomic codes - DICOM master list~^^~^^|",
            "pulmonary_artery": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^81040000^Pulmonary artery~^^~Anatomic codes - DICOM master list~^^~^^|",
            "brain": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^12738006^Brain~^^~Anatomic codes - DICOM master list~^^~^^|",
            "iliac_artery_left": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^73634005^Common iliac artery~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "iliac_artery_right": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^73634005^Common iliac artery~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "iliac_vena_left": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^46027005^Common iliac vein~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "iliac_vena_right": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^46027005^Common iliac vein~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "small_bowel": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^30315005^Small Intestine~^^~Anatomic codes - DICOM master list~^^~^^|",
            "duodenum": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^38848004^Duodenum~^^~Anatomic codes - DICOM master list~^^~^^|",
            "colon": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^71854001^Colon~^^~Anatomic codes - DICOM master list~^^~^^|",
            "rib_left_1": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^48535007^First rib~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "rib_left_2": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^78247007^Second rib~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "rib_left_3": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^25888004^Third rib~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "rib_left_4": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^25523003^Fourth rib~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "rib_left_5": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^15339008^Fifth rib~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "rib_left_6": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^59558009^Sixth rib~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "rib_left_7": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^24915002^Seventh rib~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "rib_left_8": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^5953002^Eighth rib~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "rib_left_9": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^22565002^Ninth rib~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "rib_left_10": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^77644006^Tenth rib~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "rib_left_11": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^58830002^Eleventh rib~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "rib_left_12": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^43993008^Twelfth rib~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "rib_right_1": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^48535007^First rib~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "rib_right_2": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^78247007^Second rib~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "rib_right_3": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^25888004^Third rib~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "rib_right_4": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^25523003^Fourth rib~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "rib_right_5": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^15339008^Fifth rib~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "rib_right_6": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^59558009^Sixth rib~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "rib_right_7": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^24915002^Seventh rib~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "rib_right_8": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^5953002^Eighth rib~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "rib_right_9": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^22565002^Ninth rib~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "rib_right_10": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^77644006^Tenth rib~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "rib_right_11": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^58830002^Eleventh rib~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "rib_right_12": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^43993008^Twelfth rib~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "humerus_left": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^85050009^Humerus~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "humerus_right": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^85050009^Humerus~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "scapula_left": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^79601000^Scapula~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "scapula_right": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^79601000^Scapula~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "clavicula_left": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^51299004^Clavicle~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "clavicula_right": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^51299004^Clavicle~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "femur_left": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^71341001^Femur~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "femur_right": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^71341001^Femur~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "hip_left": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^29836001^Hip~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "hip_right": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^29836001^Hip~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "sacrum": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^54735007^Sacrum~^^~Anatomic codes - DICOM master list~^^~^^|",
            "face": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^89545001^Face~^^~Anatomic codes - DICOM master list~^^~^^|",
            "gluteus_maximus_left": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^181674001^Gluteus maximus muscle~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "gluteus_maximus_right": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^181674001^Gluteus maximus muscle~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "gluteus_medius_left": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^78333006^Gluteus medius muscle~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "gluteus_medius_right": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^78333006^Gluteus medius muscle~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "gluteus_minimus_left": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^78333006^Gluteus medius muscle~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "gluteus_minimus_right": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^78333006^Gluteus medius muscle~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "autochthon_left": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^44947003^Erector spinae muscle~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "autochthon_right": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^44947003^Erector spinae muscle~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "iliopsoas_left": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^68455001^Iliopsoas muscle~SCT^7771000^Left~Anatomic codes - DICOM master list~^^~^^|",
            "iliopsoas_right": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^68455001^Iliopsoas muscle~SCT^24028007^Right~Anatomic codes - DICOM master list~^^~^^|",
            "urinary_bladder": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^89837001^Bladder~^^~Anatomic codes - DICOM master list~^^~^^|",

            # SPecification of these codes are still work in progress:
            #"femur": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^71341001^Femur~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"patella": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^64234005^Patella~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"tibia": "",
            #"fibula": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^87342007^Fibula~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"tarsal": "",
            #"metatarsal": "",
            #"phalanges_feet": "",
            #"humerus": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^85050009^Humerus~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"ulna": "",
            #"radius": "",
            #"carpal": "",
            #"metacarpal": "",
            #"phalanges_hand": "",
            #"sternum": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^56873002^Sternum~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"skull": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^89546000^Skull~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"subcutaneous_fat": "",
            #"skeletal_muscle": "",
            #"torso_fat": "",
            #"spinal_cord": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^2748008^Spinal cord~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"lung_covid_infiltrate": "",
            #"intracerebral_hemorrhage": "",
            #"hip_implant": "Segmentation category and type - DICOM master list~SCT^260787004^Physical object~SCT^40388003^Implant~^^~Anatomic codes - DICOM master list~SCT^24136001^Hip joint~SCT^51440002^Right and left|",
            #"coronary_arteries": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^41801008^Coronary artery~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"kidney": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^64033007^Kidney~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"adrenal_gland": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^23451007^Adrenal gland~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"vertebrae_lumbar": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^51282000^Vertebra~^^~Anatomic codes - DICOM master list~SCT^122496007^Lumbar spine~^^|",
            #"vertebrae_thoracic": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^51282000^Vertebra~^^~Anatomic codes - DICOM master list~SCT^122495006^Thoracic spine~^^|",
            #"vertebrae_cervical": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^51282000^Vertebra~^^~Anatomic codes - DICOM master list~SCT^122494005^Cervical spine~^^|",
            #"iliac_artery": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^73634005^Common iliac artery~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"iliac_vena": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^46027005^Common iliac vein~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"ribs": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^113197003^Rib~^^~Anatomic codes - DICOM master list~SCT^39607008^Lung~SCT^24028007^Right|",
            #"scapula": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^79601000^Scapula~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"clavicula": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^51299004^Clavicle~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"hip": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^29836001^Hip~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"gluteus_maximus": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^181674001^Gluteus maximus muscle~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"gluteus_medius": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^78333006^Gluteus medius muscle~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"gluteus_minimus": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^78333006^Gluteus medius muscle~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"autochthon": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^44947003^Erector spinae muscle~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"iliopsoas": "Segmentation category and type - Total Segmentator~SCT^123037004^Anatomical Structure~SCT^68455001^Iliopsoas muscle~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"lung_vessels": "Segmentation category and type - DICOM master list~SCT^85756007^Tissue~SCT^59820001^Blood vessel~^^~Anatomic codes - DICOM master list~SCT^39607008^Lung~SCT^24028007^Right|",
            #"lung_trachea_bronchia": "Segmentation category and type - DICOM master list~SCT^123037004^Anatomical Structure~SCT^110726009^Trachea and bronchus~^^~Anatomic codes - DICOM master list~^^~^^|",
            #"body_trunc": "",
            #"body_extremities": "",
            #"lung_pleural": "",
            #"pleural_effusion": "",
            #"pericardial_effusion": "",
        }

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
        tlogic.DeserializeTerminologyEntry(terminologyEntryStr, terminologyEntry)

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

    def setupPythonRequirements(self, upgrade=False):

        # Install PyTorch
        try:
          import PyTorchUtils
        except ModuleNotFoundError as e:
          raise RuntimeError("This module requires PyTorch extension. Install it from the Extensions Manager.")

        torchLogic = PyTorchUtils.PyTorchUtilsLogic()
        if not torchLogic.torchInstalled():
            self.log('PyTorch Python package is required. Installing... (it may take several minutes)')
            torch = torchLogic.installTorch(askConfirmation=True)
            if torch is None:
                raise ValueError('PyTorch extension needs to be installed to use this module.')

        # nnunet\training\network_training\nnUNetTrainer.py requires matplotlib
        needToInstallMatplotlib = False
        try:
            import matplotlib
        except ModuleNotFoundError as e:
            needToInstallMatplotlib = True
        if needToInstallMatplotlib:
            self.log('Matplotlib Python package is required. Installing...')
            slicer.util.pip_install("matplotlib")

        # Install TotalSegmentator segmenter

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
            self.log('TotalSegmentator Python package is required. Installing... (it may take several minutes)')

            if upgrade:
                # TotalSegmentator version information is usually not updated with each git revision, therefore we must uninstall it to force the upgrade
                slicer.util.pip_uninstall("TotalSegmentator")
                # Update TotalSegmentator and all its dependencies
                slicer.util.pip_install(self.totalSegmentatorPythonPackageDownloadUrl + " --upgrade")
            else:
                # Install TotalSegmentator and all its dependencies
                slicer.util.pip_install(self.totalSegmentatorPythonPackageDownloadUrl)

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

    def process(self, inputVolume, outputSegmentation, fast=True, task=None):

        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param inputVolume: volume to be thresholded
        :param outputVolume: thresholding result
        :param fast: faster and less accurate output
        :param task: one of self.tasks, default is "total"
        """

        if not inputVolume:
            raise ValueError("Input or output volume is invalid")

        if task == None:
            task = "total"

        import time
        startTime = time.time()
        self.log('Processing started')

        # Create new empty folder
        tempFolder = slicer.util.tempDirectory()

        inputFile = tempFolder+"/total-segmentator-input.nii"
        outputSegmentationFolder = tempFolder + "/segmentation"
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
            fast = mbox.exec_()

        if not fast and cuda and cuda.get_device_properties(cuda.current_device()).total_memory < 7e9:
            if slicer.util.confirmYesNoDisplay("You have less than 7 GB of GPU memory available. Enable 'fast' mode to ensure segmentation can be completed successfully?"):
                fast = True

        # Get TotalSegmentator launcher command
        # TotalSegmentator (.py file, without extension) is installed in Python Scripts folder
        import sysconfig
        totalSegmentatorPath = os.path.join(sysconfig.get_path('scripts'), "TotalSegmentator")
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
        self.log('Creating segmentations with TotalSegmentator AI...')
        self.log(f"Total Segmentator arguments: {options}")
        proc = slicer.util.launchConsoleProcess(totalSegmentatorCommand + options)
        self.logProcessOutput(proc)

        # Load result
        self.log('Importing segmentation results...')
        if multilabel:
            self.readSegmentation(outputSegmentation, outputSegmentationFile, task)
        else:
            self.readSegmentationFolder(outputSegmentation, outputSegmentationFolder, task)

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

        stopTime = time.time()
        self.log(f'Processing completed in {stopTime-startTime:.2f} seconds')

    def readSegmentationFolder(self, outputSegmentation, output_segmentation_dir, task):
        """The method is very slow, but this is the only option for some specialized tasks.
        """

        from os.path import exists

        outputSegmentation.GetSegmentation().RemoveAllSegments()

        # Get label descriptions
        from totalsegmentator.map_to_binary import class_map
        labelValueToSegmentName = class_map[task]

        # Get color node with random colors
        randomColorsNode = slicer.mrmlScene.GetNodeByID('vtkMRMLColorTableNodeRandom')
        rgba = [0, 0, 0, 0]

        # Read each candidate file
        for labelValue in labelValueToSegmentName:
            segmentName = labelValueToSegmentName[labelValue]
            self.log(f"Importing {segmentName}")
            labelVolumePath = f"{output_segmentation_dir}/{segmentName}.nii.gz"
            if not exists(labelVolumePath):
                continue

            labelmapVolumeNode = slicer.util.loadLabelVolume(labelVolumePath, {"name": segmentName})

            randomColorsNode.GetColor(labelValue,rgba)
            segmentId = outputSegmentation.GetSegmentation().AddEmptySegment(segmentName, segmentName, rgba[0:3])
            updatedSegmentIds = vtk.vtkStringArray()
            updatedSegmentIds.InsertNextValue(segmentId)
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelmapVolumeNode, outputSegmentation, updatedSegmentIds)
            self.setTerminology(outputSegmentation, segmentName, segmentId)

            slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

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

            self.delayDisplay('Set up required Python packages')
            logic.setupPythonRequirements()

            self.delayDisplay('Compute output')
            logic.process(inputVolume, outputSegmentation)

        else:
            logging.warning("test_TotalSegmentator1 logic testing was skipped")

        self.delayDisplay('Test passed')
