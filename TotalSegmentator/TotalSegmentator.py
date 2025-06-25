import logging
import os
import re

import vtk

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
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
        self.parent.title = _("Total Segmentator")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Segmentation")]
        self.parent.dependencies = []
        self.parent.contributors = ["Andras Lasso (PerkLab, Queen's University)"]
        self.parent.helpText = _("""
3D Slicer extension for fully automatic whole body CT segmentation using "TotalSegmentator" AI model.
See more information in the <a href="https://github.com/lassoan/SlicerTotalSegmentator">extension documentation</a>.
""")
        self.parent.acknowledgementText = _("""
This file was originally developed by Andras Lasso (PerkLab, Queen's University).
The module uses <a href="https://github.com/wasserth/TotalSegmentator">TotalSegmentator</a>.
If you use the TotalSegmentator nn-Unet function from this software in your research, please cite:
Wasserthal J., Meyer M., , Hanns-Christian Breit H.C., Cyriac J., Shan Y., Segeroth, M.:
TotalSegmentator: robust segmentation of 104 anatomical structures in CT images.
https://arxiv.org/abs/2208.05868
""")
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
            taskTitle = self.logic.tasks[task]['title']
            if self.logic.isLicenseRequiredForTask(task):
                taskTitle = _("{task_title} [license required]").format(task_title=taskTitle)
            self.ui.taskComboBox.addItem(taskTitle, task)

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
            self.ui.applyButton.toolTip = _("Start segmentation")
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = _("Select input volume")
            self.ui.applyButton.enabled = False

        if inputVolume:
            self.ui.outputSegmentationSelector.baseName = _("{volume_name} segmentation").format(volume_name=inputVolume.GetName())

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
        self.ui.statusLabel.plainText = ''

        import qt

        sequenceBrowserNode = slicer.modules.sequences.logic().GetFirstBrowserNodeForProxyNode(self.ui.inputVolumeSelector.currentNode())
        if sequenceBrowserNode:
            if not slicer.util.confirmYesNoDisplay(_("The input volume you provided are part of a sequence. Do you want to segment all frames of that sequence?")):
                sequenceBrowserNode = None

        try:
            slicer.app.setOverrideCursor(qt.Qt.WaitCursor)
            self.logic.setupPythonRequirements()
            slicer.app.restoreOverrideCursor()
        except Exception as e:
            slicer.app.restoreOverrideCursor()
            import traceback
            traceback.print_exc()
            self.ui.statusLabel.appendPlainText(_("Failed to install Python dependencies:\n{exception}\n").format(exception=e))
            restartRequired = False
            if isinstance(e, InstallError):
                restartRequired = e.restartRequired
            if restartRequired:
                self.ui.statusLabel.appendPlainText("\n" + _("Application restart required."))
                if slicer.util.confirmOkCancelDisplay(
                    _("Application is required to complete installation of required Python packages.\nPress OK to restart."),
                    _("Confirm application restart"),
                    detailedText=str(e)
                    ):
                    slicer.util.restart()
                else:
                    return
            else:
                slicer.util.errorDisplay(_("Failed to install required packages.\n\n{exception}").format(exception=e))
                return

        with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):

            # Create new segmentation node, if not selected yet
            if not self.ui.outputSegmentationSelector.currentNode():
                self.ui.outputSegmentationSelector.addNode()

            self.logic.useStandardSegmentNames = self.ui.useStandardSegmentNamesCheckBox.checked

            # Compute output
            self.logic.process(self.ui.inputVolumeSelector.currentNode(), self.ui.outputSegmentationSelector.currentNode(),
                self.ui.fastCheckBox.checked, self.ui.cpuCheckBox.checked, self.ui.taskComboBox.currentData, interactive = True, sequenceBrowserNode = sequenceBrowserNode)

        self.ui.statusLabel.appendPlainText("\n" + _("Processing finished."))

    def onPackageInfoUpdate(self):
        self.ui.packageInfoTextBrowser.plainText = ''
        with slicer.util.tryWithErrorDisplay(_("Failed to get TotalSegmentator package version information"), waitCursor=True):
            self.ui.packageInfoTextBrowser.plainText = self.logic.installedTotalSegmentatorPythonPackageInfo().rstrip()

    def onPackageUpgrade(self):
        with slicer.util.tryWithErrorDisplay(_("Failed to upgrade TotalSegmentator"), waitCursor=True):
            self.logic.setupPythonRequirements(upgrade=True)
        self.onPackageInfoUpdate()
        if not slicer.util.confirmOkCancelDisplay(_("This TotalSegmentator update requires a 3D Slicer restart."),_("Press OK to restart.")):
            raise ValueError(_("Restart was cancelled."))
        else:
            slicer.util.restart()

    def onSetLicense(self):
        import qt
        licenseText = qt.QInputDialog.getText(slicer.util.mainWindow(), _("Set TotalSegmentator license key"), _("License key:"))

        success = False
        with slicer.util.tryWithErrorDisplay(_("Failed to set TotalSegmentator license."), waitCursor=True):
            if not licenseText:
                raise ValueError(_("License is not specified."))
            self.logic.setupPythonRequirements()
            self.logic.setLicense(licenseText)
            success = True

        if success:
            slicer.util.infoDisplay(_("License key is set. You can now use TotalSegmentator tasks that require a license."))


#
# TotalSegmentatorLogic
#

class InstallError(Exception):
    def __init__(self, message, restartRequired=False):
        # Call the base class constructor with the parameters it needs
        super().__init__(message)
        self.message = message
        self.restartRequired = restartRequired
    def __str__(self):
        return self.message

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

        import sys
        if sys.version_info < (3, 12):
            # Python 3.9 (Slicer-5.8 and earlier)
            self.totalSegmentatorPythonPackageDownloadUrl = "https://github.com/wasserth/TotalSegmentator/archive/25a858672cf9400e34c7421e9635dca23770344b.zip"  # latest version (post 2.6.0) as of 2025-02-16
        else:
            # Python >= 3.12 (Slicer-5.9 and later)
            self.totalSegmentatorPythonPackageDownloadUrl = "https://github.com/wasserth/TotalSegmentator/archive/0a1c3c31588487e64ba1d43996f3934afd0e4bb9.zip"  # latest version (post 2.9.0) as of 2025-06-20

        # Custom applications can set custom location for weights.
        # For example, it could be set to `sysconfig.get_path('scripts')` to have an independent copy of
        # the weights for each Slicer installation. However, setting such custom path would result in extra downloads and
        # storage space usage if there were multiple Slicer installations on the same computer.
        self.totalSegmentatorWeightsPath = None

        self.logCallback = None
        self.clearOutputFolder = True
        self.useStandardSegmentNames = True
        self.pullMaster = False

        # List of property type codes that are specified by in the TotalSegmentator terminology.
        #
        # # Codes are stored as a list of strings containing coding scheme designator and code value of the property type,
        # separated by "^" character. For example "SCT^123456".
        #
        # If property the code is found in this list then the TotalSegmentator terminology will be used,
        # otherwise the DICOM terminology will be used. This is necessary because the DICOM terminology
        # does not contain all the necessary items and some items are incomplete (e.g., don't have color or 3D Slicer label).
        #
        self.totalSegmentatorTerminologyPropertyTypes = []

        # Map from TotalSegmentator structure name to terminology string.
        # Terminology string uses Slicer terminology entry format - see specification at
        # https://slicer.readthedocs.io/en/latest/developer_guide/modules/segmentations.html#terminologyentry-tag
        self.totalSegmentatorLabelTerminology = {}

        # Segmentation tasks specified by TotalSegmentator
        # Ideally, this information should be provided by TotalSegmentator itself.
        self.tasks = OrderedDict()

        # Main
        self.tasks['total'] = {'title': 'total', 'modalities': ['CT'], 'supportsFast': True, 'supportsFastest': True, 'supportsMultiLabel': True}
        self.tasks['total_mr'] = {'title': 'total (MR)', 'modalities': ['MR'], 'supportsFast': True, 'supportsFastest': True, 'supportsMultiLabel': True}
        self.tasks['vertebrae_mr'] = {'title': 'vertebrae (MR)',  'modalities': ['MR'], 'description:': 'acrum, vertebrae L1-5, vertebrae T1-12, vertebrae C1-7 (for CT this is part of the `total` task)', 'supportsMultiLabel': True}
        self.tasks['lung_nodules'] = {'title': 'lung: nodules', 'modalities': ['CT'], 'description': 'lung, lung_nodules (provided by [BLUEMIND AI](https://bluemind.co/): Fitzjalen R., Aladin M., Nanyan G.) (trained on 1353 subjects, partly from LIDC-IDRI)', 'supportsMultiLabel': True}
        self.tasks['lung_vessels'] = {'title': 'lung: vessels'}

        self.tasks['kidney_cysts'] = {'title': 'kidney: cysts', 'modalities': ['CT'], 'description': 'kidney_cyst_left, kidney_cyst_right (strongly improved accuracy compared to kidney_cysts inside of `total` task)', 'supportsMultiLabel': True}
        self.tasks['breasts'] = {'title': 'breasts', 'modalities': ['CT'], 'supportsMultiLabel': True}
        self.tasks['liver_segments'] = {'title': 'liver: segments', 'modalities': ['CT'], 'description': 'liver_segment_1, liver_segment_2, liver_segment_3, liver_segment_4, liver_segment_5, liver_segment_6, liver_segment_7, liver_segment_8 (Couinaud segments)', 'supportsMultiLabel': True}
        self.tasks['liver_segments_mr'] = {'title': 'liver: segments (MR)', 'modalities': ['MR'], 'description': 'liver_segment_1, liver_segment_2, liver_segment_3, liver_segment_4, liver_segment_5, liver_segment_6, liver_segment_7, liver_segment_8 (for MR images) (Couinaud segments)', 'supportsMultiLabel': True}
        self.tasks['liver_vessels'] = {'title': 'liver: vessels', 'supportsMultiLabel': True}

        self.tasks['body'] = {'title': 'body', 'supportsFast': True}
        self.tasks['body_mr'] = {'title': 'body (MR)',  'modalities': ['MR'], 'description:': 'body_trunc, body_extremities (for MR images)', 'supportsFast': True, 'supportsMultiLabel': True}

        self.tasks['head_glands_cavities'] = {'title': 'head: glands and cavities', 'supportsMultiLabel': True}
        self.tasks['head_muscles'] = {'title': 'head: muscles', 'supportsMultiLabel': True}
        self.tasks['oculomotor_muscles'] = {'title': 'head: oculomotor muscles', 'modalities': ['CT'], 'description': 'skull, eyeball_right, lateral_rectus_muscle_right, superior_oblique_muscle_right, levator_palpebrae_superioris_right, superior_rectus_muscle_right, medial_rectus_muscle_left, inferior_oblique_muscle_right, inferior_rectus_muscle_right, optic_nerve_left, eyeball_left, lateral_rectus_muscle_left, superior_oblique_muscle_left, levator_palpebrae_superioris_left, superior_rectus_muscle_left, medial_rectus_muscle_right, inferior_oblique_muscle_left, inferior_rectus_muscle_left, optic_nerve_right', 'supportsMultiLabel': True}
        self.tasks['headneck_bones_vessels'] = {'title': 'head and neck: bones and vessels', 'supportsMultiLabel': True}
        self.tasks['headneck_muscles'] = {'title': 'head and neck: muscles', 'supportsMultiLabel': True}

        # Trained on reduced data set
        self.tasks['cerebral_bleed'] = {'title': 'brain: cerebral bleed', 'supportsMultiLabel': True}
        self.tasks['hip_implant'] = {'title': 'hip implant', 'supportsMultiLabel': True}
        self.tasks['pleural_pericard_effusion'] = {'title': 'heart: pleural and pericardial effusion', 'supportsMultiLabel': True}

        # Requires license
        self.tasks['coronary_arteries'] = {'title': 'heart: coronary arteries', 'description': 'coronary_arteries (also works on non-contrast images)', 'supportsMultiLabel': True, 'requiresLicense': True}
        self.tasks['vertebrae_body'] = {'title': 'vertebrae body', 'requiresLicense': True}
        self.tasks['appendicular_bones'] = {'title': 'appendicular bones', 'supportsMultiLabel': True, 'requiresLicense': True}
        self.tasks['appendicular_bones_mr'] = {'title': 'appendicular bones (MR)', 'modalities': ['MR'], 'description': 'patella, tibia, fibula, tarsal, metatarsal, phalanges_feet, ulna, radius (for MR images)', 'supportsMultiLabel': True, 'requiresLicense': True}
        self.tasks['tissue_types'] = {'title': 'tissue types', 'supportsMultiLabel': True, 'requiresLicense': True}
        self.tasks['tissue_4_types'] = {'title': 'tissue 4 types', 'description': 'subcutaneous_fat, torso_fat, skeletal_muscle, intermuscular_fat (in contrast to `tissue_types` skeletal_muscle is split into two classes: muscle and fat)', 'supportsMultiLabel': True, 'requiresLicense': True}
        self.tasks['tissue_types_mr'] = {'title': 'tissue types (MR)', 'modalities': ['MR'], 'supportsMultiLabel': True, 'requiresLicense': True}
        self.tasks['heartchambers_highres'] = {'title': 'heart: chambers highres' , 'supportsMultiLabel': True, 'requiresLicense': True}
        self.tasks['face'] = {'title': 'face', 'supportsMultiLabel': True, 'requiresLicense': True}
        self.tasks['face_mr'] = {'title': 'face (MR)', 'modalities': ['MR'], 'description': 'face_region (for anonymization)', 'supportsMultiLabel': True, 'requiresLicense': True}
        self.tasks['brain_structures'] = {'title': 'brain: structures', 'supportsMultiLabel': True, 'requiresLicense': True}

        self.tasks['thigh_shoulder_muscles'] = {'title': 'thigh and shoulder: muscles', 'description': 'quadriceps_femoris_left, quadriceps_femoris_right, thigh_medial_compartment_left, thigh_medial_compartment_right, thigh_posterior_compartment_left, thigh_posterior_compartment_right, sartorius_left, sartorius_right, deltoid, supraspinatus, infraspinatus, subscapularis, coracobrachial, trapezius, pectoralis_minor, serratus_anterior, teres_major, triceps_brachi', 'supportsMultiLabel': True, 'requiresLicense': True}
        self.tasks['thigh_shoulder_muscles_mr'] = {'title': 'thigh and shoulder: muscles (MR)', 'description': 'quadriceps_femoris_left, quadriceps_femoris_right, thigh_medial_compartment_left, thigh_medial_compartment_right, thigh_posterior_compartment_left, thigh_posterior_compartment_right, sartorius_left, sartorius_right, deltoid, supraspinatus, infraspinatus, subscapularis, coracobrachial, trapezius, pectoralis_minor, serratus_anterior, teres_major, triceps_brachi (for MR images)', 'supportsMultiLabel': True, 'requiresLicense': True}

        # Experimental
        # self.tasks['ventricle_parts'] = {'title': 'ventricle_parts', 'supportsFast': False, 'supportsMultiLabel': True, 'requiresLicense': False}
        # self.tasks['aortic_sinuses'] = {'title': 'aortic_sinuses', 'supportsFast': False, 'supportsMultiLabel': True, 'requiresLicense': True}

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

        alteredStructureCategory = slicer.vtkSlicerTerminologyCategory()
        for i in range(numberOfCategories):
            terminologiesLogic.GetNthCategoryInTerminology(totalSegmentatorTerminologyName, i, alteredStructureCategory)
            if alteredStructureCategory.GetCodingSchemeDesignator() == 'SCT' and alteredStructureCategory.GetCodeValue() == '49755003':
                # Found the (49755003, SCT, "Morphologically Altered Structure") category within DICOM master list
                break

        bodySubstanceCategory = slicer.vtkSlicerTerminologyCategory()
        for i in range(numberOfCategories):
            terminologiesLogic.GetNthCategoryInTerminology(totalSegmentatorTerminologyName, i, bodySubstanceCategory)
            if bodySubstanceCategory.GetCodingSchemeDesignator() == 'SCT' and bodySubstanceCategory.GetCodeValue() == '91720002':
                # Found the (91720002, SCT, "Body Substance") category within DICOM master list
                break

        # Retrieve all property type codes from the TotalSegmentator terminology
        self.totalSegmentatorTerminologyPropertyTypes = []
        terminologyType = slicer.vtkSlicerTerminologyType()
        numberOfTypes = terminologiesLogic.GetNumberOfTypesInTerminologyCategory(totalSegmentatorTerminologyName, anatomicalStructureCategory)
        for i in range(numberOfTypes):
            if terminologiesLogic.GetNthTypeInTerminologyCategory(totalSegmentatorTerminologyName, anatomicalStructureCategory, i, terminologyType):
                self.totalSegmentatorTerminologyPropertyTypes.append(terminologyType.GetCodingSchemeDesignator() + "^" + terminologyType.GetCodeValue())
        numberOfTypes = terminologiesLogic.GetNumberOfTypesInTerminologyCategory(totalSegmentatorTerminologyName, alteredStructureCategory)
        for i in range(numberOfTypes):
            if terminologiesLogic.GetNthTypeInTerminologyCategory(totalSegmentatorTerminologyName, alteredStructureCategory, i, terminologyType):
                self.totalSegmentatorTerminologyPropertyTypes.append(terminologyType.GetCodingSchemeDesignator() + "^" + terminologyType.GetCodeValue())
        numberOfTypes = terminologiesLogic.GetNumberOfTypesInTerminologyCategory(totalSegmentatorTerminologyName, bodySubstanceCategory)
        for i in range(numberOfTypes):
            if terminologiesLogic.GetNthTypeInTerminologyCategory(totalSegmentatorTerminologyName, bodySubstanceCategory, i, terminologyType):
                self.totalSegmentatorTerminologyPropertyTypes.append(terminologyType.GetCodingSchemeDesignator() + "^" + terminologyType.GetCodeValue())

        # Helper function to get code string from CSV file row
        def getCodeString(field, columnNames, row):
            columnValues = []
            for fieldName in ["CodingScheme", "CodeValue", "CodeMeaning"]:
                columnIndex = columnNames.index(f"{field}_{fieldName}")
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
                    # Property category: "SCT^123037004^Anatomical Structure" or "SCT^49755003^Morphologically Altered Structure"
                    + '^'.join(getCodeString("Category", columnNames, row))
                    + '~'
                    # Property type: "SCT^23451007^Adrenal gland", "SCT^367643001^Cyst", ...
                    + '^'.join(getCodeString("Type", columnNames, row))
                    + '~'
                    # Property type modifier: "SCT^7771000^Left", ...
                    + '^'.join(getCodeString("TypeModifier", columnNames, row))
                    + '~Anatomic codes - DICOM master list'
                    + '~'
                    # Anatomic region (set if category is not anatomical structure): "SCT^64033007^Kidney", ...
                    + '^'.join(getCodeString("Region", columnNames, row))
                    + '~'
                    # Anatomic region modifier: "SCT^7771000^Left", ...
                    + '^'.join(getCodeString("RegionModifier", columnNames, row))
                    + '|')
                terminologyEntry = slicer.vtkSlicerTerminologyEntry()
                terminologyPropertyTypeStr = (  # Example: SCT^23451007
                    row[columnNames.index("Type_CodingScheme")]
                    + "^" + row[columnNames.index("Type_CodeValue")])
                if terminologyPropertyTypeStr in self.totalSegmentatorTerminologyPropertyTypes:
                    terminologyEntryStr = "Segmentation category and type - Total Segmentator" + terminologyEntryStrWithoutCategoryName
                else:
                    terminologyEntryStr = "Segmentation category and type - DICOM master list" + terminologyEntryStrWithoutCategoryName

                # Store the terminology string for this structure
                totalSegmentatorStructureName = row[columnNames.index("Name")]  # TotalSegmentator structure name, such as "adrenal_gland_left"
                self.totalSegmentatorLabelTerminology[totalSegmentatorStructureName] = terminologyEntryStr


    def isFastModeSupportedForTask(self, task):
        return (task in self.tasks) and ('supportsFast' in self.tasks[task]) and self.tasks[task]['supportsFast']

    def isMultiLabelSupportedForTask(self, task):
        return (task in self.tasks) and ('supportsMultiLabel' in self.tasks[task]) and self.tasks[task]['supportsMultiLabel']

    def isLicenseRequiredForTask(self, task):
        return (task in self.tasks) and ('requiresLicense' in self.tasks[task]) and self.tasks[task]['requiresLicense']

    def getSegmentLabelColor(self, terminologyEntryStr):
        """Get segment label and color from terminology"""

        def labelColorFromTypeObject(typeObject, typeModifierObject=None):
            if typeModifierObject is not None:
                if typeModifierObject.GetSlicerLabel():
                    # Slicer label is specified for the modifier that includes the full name, use that
                    label = typeModifierObject.GetSlicerLabel()
                else:
                    # Slicer label is not specified, assemble label from type and modifier
                    typeLabel = typeObject.GetSlicerLabel() if typeObject.GetSlicerLabel() else typeObject.GetCodeMeaning()
                    label = f"{typeLabel} {typeModifierObject.GetCodeMeaning()}"
                rgb = typeModifierObject.GetRecommendedDisplayRGBValue()
                if rgb[0] == 127 and rgb[1] == 127 and rgb[2] == 127:
                    # Type modifier did not have color specified, try to use the color of the type
                    rgb = typeObject.GetRecommendedDisplayRGBValue()
                return label, (rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
            label = typeObject.GetSlicerLabel() if typeObject.GetSlicerLabel() else typeObject.GetCodeMeaning()
            rgb = typeObject.GetRecommendedDisplayRGBValue()
            return label, (rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)

        tlogic = slicer.modules.terminologies.logic()

        terminologyEntry = slicer.vtkSlicerTerminologyEntry()
        if not tlogic.DeserializeTerminologyEntry(terminologyEntryStr, terminologyEntry):
            raise RuntimeError(_("Failed to deserialize terminology string: {terminology_entry_str}").format(terminology_entry_str=terminologyEntryStr))

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
                    return labelColorFromTypeObject(foundTerminologyEntry.GetTypeObject(), foundTerminologyEntry.GetTypeModifierObject())
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
        # User Latin-1 encoding to read the file, as it may contain non-ASCII characters and not necessarily in UTF-8 encoding.
        filteredMetadata = ""
        with open(metadataPath.locate(), "r+", encoding="latin1") as file:
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
                # Rewrite optional depdendencies info returned by importlib.metadata.requires to be valid for pip_install:
                # Requirement Original: ruff; extra == "dev"
                # Requirement Rewritten: ruff
                match = re.match(r"([\S]+)[\s]*; extra == \"([^\"]+)\"", requirement)
                if match:
                    requirement = f"{match.group(1)}"
            if not match:
                # nibabel >=2.3.0 -> rewrite to: nibabel>=2.3.0
                match = re.match(r"([\S]+)[\s](.+)", requirement)
                if match:
                    requirement = f"{match.group(1)}{match.group(2)}"

            if skipThisPackage:
                self.log(_('- Skip {requirement}').format(requirement))
            else:
                self.log(_('- Installing {requirement}...').format(requirement))
                slicer.util.pip_install(requirement)

        return skippedRequirements

    def setupPythonRequirements(self, upgrade=False):
        import importlib.metadata
        import importlib.util
        import packaging

        # TotalSegmentator requires this, yet it is not listed among its dependencies
        try:
            import pandas
        except ModuleNotFoundError as e:
            slicer.util.pip_install("pandas")

        # TotalSegmentator requires dicom2nifti (we don't use any DICOM features in Slicer but DICOM support is not optional in TotalSegmentator)
        # but latest dicom2nifti is broken on Python-3.9. We need to install an older version.
        # (dicom2nifti was recently updated to version 2.6. This version needs pydicom >= 3.0.0, which requires python >= 3.10)
        try:
            import dicom2nifti
        except ModuleNotFoundError as e:
            slicer.util.pip_install("dicom2nifti<=2.5.1")

        # These packages come preinstalled with Slicer and should remain unchanged
        packagesToSkip = [
            'SimpleITK',  # Slicer's SimpleITK uses a special IO class, which should not be replaced
            'torch',  # needs special installation using SlicerPyTorch
            'nnunetv2',  # needs special installation using SlicerNNUNet
            'requests',  # TotalSegmentator would want to force a specific version of requests, which would require a restart of Slicer and it is unnecessary
            'rt_utils',  # Only needed for RTSTRUCT export, which is not needed in Slicer; rt_utils depends on opencv-python which is hard to build
            'dicom2nifti', # We already installed a known working version, do not let TotalSegmentator to upgrade to a newer version that may not work on Python-3.9
            ]

        # Ask for confirmation before installing PyTorch and nnUNet
        confirmPackagesToInstall = []

        try:
          import PyTorchUtils
        except ModuleNotFoundError as e:
          raise InstallError("This module requires PyTorch extension. Install it from the Extensions Manager.")

        minimumTorchVersion = "2.0.0"  # per https://github.com/wasserth/TotalSegmentator/blob/7274faac4673298d17b63a5a8335006f02e6d426/setup.py#L19
        torchLogic = PyTorchUtils.PyTorchUtilsLogic()
        if not torchLogic.torchInstalled():
            confirmPackagesToInstall.append("PyTorch")

        try:
            import SlicerNNUNetLib
        except ModuleNotFoundError as e:
            raise InstallError("This module requires SlicerNNUNet extension. Install it from the Extensions Manager.")

        minimumNNUNetVersion = "2.2.1"  # per https://github.com/wasserth/TotalSegmentator/blob/7274faac4673298d17b63a5a8335006f02e6d426/setup.py#L26
        nnunetlogic = SlicerNNUNetLib.InstallLogic(doAskConfirmation=False)
        nnunetlogic.getInstalledNNUnetVersion()
        from packaging.requirements import Requirement
        if not nnunetlogic.isPackageInstalled(Requirement("nnunetv2")):
            confirmPackagesToInstall.append("nnunetv2")

        if confirmPackagesToInstall:
            if not slicer.util.confirmOkCancelDisplay(
                _("This module requires installation of additional Python packages. Installation needs network connection and may take several minutes. Click OK to proceed."),
                _("Confirm Python package installation"),
                detailedText=_("Python packages that will be installed: {package_list}").format(package_list=', '.join(confirmPackagesToInstall))
                ):
                raise InstallError("User cancelled.")

        # Install PyTorch
        if "PyTorch" in confirmPackagesToInstall:
            self.log(_('PyTorch Python package is required. Installing... (it may take several minutes)'))
            torch = torchLogic.installTorch(askConfirmation=False, torchVersionRequirement = f">={minimumTorchVersion}")
            if torch is None:
                raise InstallError("This module requires PyTorch extension. Install it from the Extensions Manager.")
        else:
            # torch is installed, check version
            from packaging import version
            if version.parse(torchLogic.torch.__version__) < version.parse(minimumTorchVersion):
                raise InstallError(f'PyTorch version {torchLogic.torch.__version__} is not compatible with this module.'
                                 + f' Minimum required version is {minimumTorchVersion}. You can use "PyTorch Util" module to install PyTorch'
                                 + f' with version requirement set to: >={minimumTorchVersion}')

        # Install nnUNet
        if "nnunetv2" in confirmPackagesToInstall:
            self.log(_('nnunetv2 package is required. Installing... (it may take several minutes)'))
            nnunet = nnunetlogic.setupPythonRequirements(f"nnunetv2>={minimumNNUNetVersion}")
            if not nnunet:
                raise InstallError("This module requires SlicerNNUNet extension. Install it from the Extensions Manager.")
        else:
            installed_nnunet_version = nnunetlogic.getInstalledNNUnetVersion()
            if installed_nnunet_version < version.parse(minimumNNUNetVersion):
                raise InstallError(f'nnUNetv2 version {installed_nnunet_version} is not compatible with this module.'
                                 + f' Minimum required version is {minimumNNUNetVersion}. You can use "nnUNet" module to install nnUNet'
                                 + f' with version requirement set to: >={minimumNNUNetVersion}')

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
                        _("This module requires TotalSegmentator Python package update."),
                        detailedText=_("Currently installed: {downloadUrl}\n\nRequired: {requiredUrl}").format(downloadUrl, requiredUrl=self.totalSegmentatorPythonPackageDownloadUrl)):
                      raise ValueError('TotalSegmentator update was cancelled.')
                    upgrade = True
        except ModuleNotFoundError as e:
            needToInstallSegmenter = True

        if needToInstallSegmenter or upgrade:
            self.log(_('TotalSegmentator Python package is required. Installing it from {downloadUrl}... (it may take several minutes)').format(downloadUrl=self.totalSegmentatorPythonPackageDownloadUrl))

            if upgrade:
                # TotalSegmentator version information is usually not updated with each git revision, therefore we must uninstall it to force the upgrade
                slicer.util.pip_uninstall("TotalSegmentator")

            # Update TotalSegmentator and all its dependencies
            self.pipInstallSelective(
                "TotalSegmentator",
                self.totalSegmentatorPythonPackageDownloadUrl + (" --upgrade" if upgrade else ""),
                packagesToSkip)

            self.log(_('TotalSegmentator installation completed successfully.'))


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

    def logProcessOutput(self, proc, returnOutput=False):
        # Wait for the process to end and forward output to the log
        output = ""
        from subprocess import CalledProcessError
        while True:
            try:
                line = proc.stdout.readline()
                if not line:
                    break
                if returnOutput:
                    output += line
                self.log(line.rstrip())
            except UnicodeDecodeError as e:
                # Code page conversion happens because `universal_newlines=True` sets process output to text mode,
                # and it fails because probably system locale is not UTF8. We just ignore the error and discard the string,
                # as we only guarantee correct behavior if an UTF8 locale is used.
                pass

        proc.wait()
        retcode = proc.returncode
        if retcode != 0:
            raise CalledProcessError(retcode, proc.args, output=proc.stdout, stderr=proc.stderr)
        return output if returnOutput else None


    def check_zip_extension(self, file_path):
        _, ext = os.path.splitext(file_path)

        if ext.lower() != '.zip':
            raise ValueError(f"The selected file '{file_path}' is not a .zip file!")

    @staticmethod
    def executableName(name):
        return name + ".exe" if os.name == "nt" else name

    def setLicense(self, licenseStr):

        """
        Import weights.
        Weights are provided in ZIP format.
        This function can be used without GUI widget.
        """

        # Get totalseg_import_weights command
        # totalseg_import_weights (.py file, without extension) is installed in Python Scripts folder

        if not licenseStr:
            raise ValueError(f"The license string is empty.")

        self.log(_('Setting license...'))

        # Get Python executable path
        import shutil
        pythonSlicerExecutablePath = shutil.which('PythonSlicer')
        if not pythonSlicerExecutablePath:
            raise RuntimeError("Python was not found")

        # Get arguments
        import sysconfig
        totalSegmentatorLicenseToolExecutablePath = os.path.join(sysconfig.get_path('scripts'), TotalSegmentatorLogic.executableName("totalseg_set_license"))
        cmd = [pythonSlicerExecutablePath, totalSegmentatorLicenseToolExecutablePath, "-l", licenseStr]

        # Launch command
        logging.debug(f"Launch TotalSegmentator license tool: {cmd}")
        proc = slicer.util.launchConsoleProcess(cmd)
        licenseToolOutput = self.logProcessOutput(proc, returnOutput=True)
        if "ERROR: Invalid license number" in licenseToolOutput:
            raise ValueError('Invalid license number. Please check your license number or contact support.')

        self.log(_('License has been successfully set.'))

        if slicer.util.confirmOkCancelDisplay(_("This license update requires a 3D Slicer restart.","Press OK to restart.")):
            slicer.util.restart()
        else:
            raise ValueError('Restart was cancelled.')


    def process(self, inputVolume, outputSegmentation, fast=True, cpu=False, task=None, subset=None, interactive=False, sequenceBrowserNode=None):
        """
        Run the processing algorithm on a volume or a sequence of volumes.
        Can be used without GUI widget.
        :param inputVolume: volume to be thresholded
        :param outputVolume: thresholding result
        :param fast: faster and less accurate output
        :param task: one of self.tasks, default is "total"
        :param subset: a list of structures (TotalSegmentator classe names https://github.com/wasserth/TotalSegmentator#class-detailsTotalSegmentator) to segment.
          Default is None, which means that all available structures will be segmented."
        :param interactive: set to True to enable warning popups to be shown to users
        :param sequenceBrowserNode: if specified then all frames of the inputVolume sequence will be segmented
        """

        if not inputVolume:
            raise ValueError("Input or output volume is invalid")

        if task == None and not subset:
            task = "total"

        import time
        startTime = time.time()
        self.log(_('Processing started'))

        if self.totalSegmentatorWeightsPath:
            os.environ["TOTALSEG_WEIGHTS_PATH"] = self.totalSegmentatorWeightsPath

        # Create new empty folder
        tempFolder = slicer.util.tempDirectory()

        inputFile = tempFolder+"/total-segmentator-input.nii"
        outputSegmentationFolder = tempFolder + "/segmentation"
        # print (outputSegmentationFolder)
        outputSegmentationFile = tempFolder + "/segmentation.nii"

        # Recommend the user to switch to fast mode if no GPU or not enough memory is available
        import torch

        cuda = torch.cuda if torch.backends.cuda.is_built() and torch.cuda.is_available() else None

        if not fast and not cuda and interactive:

            import ctk
            import qt
            mbox = ctk.ctkMessageBox(slicer.util.mainWindow())
            mbox.text = _("No GPU is detected. Switch to 'fast' mode to get low-resolution result in a few minutes or compute full-resolution result which may take 5 to 50 minutes (depending on computer configuration)?")
            mbox.addButton(_("Fast (~2 minutes)"), qt.QMessageBox.AcceptRole)
            mbox.addButton(_("Full-resolution (~5 to 50 minutes)"), qt.QMessageBox.RejectRole)
            # Windows 10 peek feature in taskbar shows all hidden but not destroyed windows
            # (after creating and closing a messagebox, hovering over the mouse on Slicer icon, moving up the
            # mouse to the peek thumbnail would show it again).
            mbox.deleteLater()
            fast = (mbox.exec_() == qt.QMessageBox.AcceptRole)

        if not fast and cuda and cuda.get_device_properties(cuda.current_device()).total_memory < 7e9 and interactive:
            if slicer.util.confirmYesNoDisplay(_("You have less than 7 GB of GPU memory available. Enable 'fast' mode to ensure segmentation can be completed successfully?")):
                fast = True

        # Get TotalSegmentator launcher command
        # TotalSegmentator (.py file, without extension) is installed in Python Scripts folder
        import sysconfig
        totalSegmentatorExecutablePath = os.path.join(sysconfig.get_path('scripts'), TotalSegmentatorLogic.executableName("TotalSegmentator"))
        # Get Python executable path
        import shutil
        pythonSlicerExecutablePath = shutil.which('PythonSlicer')
        if not pythonSlicerExecutablePath:
            raise RuntimeError("Python was not found")
        totalSegmentatorCommand = [ pythonSlicerExecutablePath, totalSegmentatorExecutablePath]

        inputVolumeSequence = None
        if sequenceBrowserNode:
            inputVolumeSequence = sequenceBrowserNode.GetSequenceNode(inputVolume)

        if inputVolumeSequence is not None:

            # If the volume already has a sequence in the current browser node then use that
            segmentationSequence = sequenceBrowserNode.GetSequenceNode(outputSegmentation)
            if not segmentationSequence:
                segmentationSequence = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSequenceNode", outputSegmentation.GetName())
                sequenceBrowserNode.AddProxyNode(outputSegmentation, segmentationSequence, False)

            selectedItemNumber = sequenceBrowserNode.GetSelectedItemNumber()
            sequenceBrowserNode.PlaybackActiveOff()
            sequenceBrowserNode.SelectFirstItem()
            sequenceBrowserNode.SetRecording(segmentationSequence, True)
            sequenceBrowserNode.SetSaveChanges(segmentationSequence, True)

            numberOfItems = sequenceBrowserNode.GetNumberOfItems()
            for i in range(numberOfItems):
                self.log(f"Segmenting item {i+1}/{numberOfItems} of sequence")
                self.processVolume(inputFile, inputVolume,
                                   outputSegmentationFolder, outputSegmentation, outputSegmentationFile,
                                   task, subset, cpu, totalSegmentatorCommand, fast)
                sequenceBrowserNode.SelectNextItem()
            sequenceBrowserNode.SetSelectedItemNumber(selectedItemNumber)

        else:
            # Segment a single volume
            self.processVolume(inputFile, inputVolume,
                               outputSegmentationFolder, outputSegmentation, outputSegmentationFile,
                               task, subset, cpu, totalSegmentatorCommand, fast)

        stopTime = time.time()
        self.log(_("Processing completed in {time_elapsed:.2f} seconds").format(time_elapsed=stopTime-startTime))

        if self.clearOutputFolder:
            self.log(_("Cleaning up temporary folder..."))
            if os.path.isdir(tempFolder):
                shutil.rmtree(tempFolder)
        else:
            self.log(_("Not cleaning up temporary folder: {temp_folder}").format(temp_folder=tempFolder))

    def processVolume(self, inputFile, inputVolume, outputSegmentationFolder, outputSegmentation, outputSegmentationFile, task, subset, cpu, totalSegmentatorCommand, fast):
        """Segment a single volume
        """

        # Write input volume to file
        # TotalSegmentator requires NIFTI
        self.log(_("Writing input file to {input_file}").format(input_file=inputFile))
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

        self.log(_('Creating segmentations with TotalSegmentator AI...'))
        self.log(_("Total Segmentator arguments: {options}").format(options))
        proc = slicer.util.launchConsoleProcess(totalSegmentatorCommand + options)
        self.logProcessOutput(proc)

        # Load result
        self.log(_('Importing segmentation results...'))
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

        # Get label descriptions if task is provided
        from totalsegmentator.map_to_binary import class_map
        labelValueToSegmentName = class_map[task] if task else {}

        def import_labelmap_to_segmentation(labelmapVolumeNode, segmentName, segmentId):
            updatedSegmentIds = vtk.vtkStringArray()
            updatedSegmentIds.InsertNextValue(segmentId)
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelmapVolumeNode, outputSegmentation, updatedSegmentIds)
            self.setTerminology(outputSegmentation, segmentName, segmentId)
            slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

        # Read each candidate file
        for labelValue, segmentName in labelValueToSegmentName.items():
            self.log(_("Importing candidate {segment_name}").format(segment_name=segmentName))
            labelVolumePath = os.path.join(output_segmentation_dir, f"{segmentName}.nii.gz")
            if not os.path.exists(labelVolumePath):
                self.log(_("Path {segment_name} not exists.").format(segment_name=segmentName))
                continue
            labelmapVolumeNode = slicer.util.loadLabelVolume(labelVolumePath, {"name": segmentName})
            randomColorsNode.GetColor(labelValue, rgba)
            segmentId = outputSegmentation.GetSegmentation().AddEmptySegment(segmentName, segmentName, rgba[0:3])
            import_labelmap_to_segmentation(labelmapVolumeNode, segmentName, segmentId)

        # Read each subset file if subset is provided
        if subset is not None and task is None:
            for segmentName in subset:
                self.log(_("Importing subset {segment_name}").format(segment_name=segmentName))
                labelVolumePath = os.path.join(output_segmentation_dir, f"{segmentName}.nii.gz")
                if os.path.exists(labelVolumePath):
                    labelmapVolumeNode = slicer.util.loadLabelVolume(labelVolumePath, {"name": segmentName})
                    segmentId = outputSegmentation.GetSegmentation().AddEmptySegment(segmentName, segmentName)
                    import_labelmap_to_segmentation(labelmapVolumeNode, segmentName, segmentId)
                else:
                    self.log(_("{segment_name} not found.").format(segment_name=segmentName))

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
                # Compare color to default gray (127.0/255.0) to avoid using undefined color
                if not TotalSegmentatorLogic.isDefaultColor(color):
                    segment.SetColor(color)
            except RuntimeError as e:
                self.log(str(e))

    @staticmethod
    def isDefaultColor(color):
        return all(abs(colorComponent - 127.0/255.0) < 0.01 for colorComponent in color)

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
