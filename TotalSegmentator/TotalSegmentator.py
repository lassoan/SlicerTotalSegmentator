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
        self.parent.contributors = ["Andras Lasso (PerkLab, Queen's University)", "Rudolf Bumm (KSGR)"]
        self.parent.helpText = """
Strip skull from brain MRI images using HD-BET tool.
See more information in <a href="https://github.com/lassoan/SlicerHDBrainExtraction">module documentation</a>.
"""
        self.parent.acknowledgementText = """
This file was originally developed by Andras Lasso (PerkLab, Queen's University).
The module uses <a href="https://github.com/MIC-DKFZ/HD-BET">HD-BET brain extraction toolkit</a>.
If you are using HD-BET, please cite the following publication: Isensee F, Schell M, Tursunova I, Brugnara G,
Bonekamp D, Neuberger U, Wick A, Schlemmer HP, Heiland S, Wick W, Bendszus M, Maier-Hein KH, Kickingereder P.
Automated brain extraction of multi-sequence MRI using artificial neural networks. Hum Brain Mapp. 2019; 1–13.
https://doi.org/10.1002/hbm.24750
"""

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

        self.ui.taskComboBox.addItems(self.logic.tasks)

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.ui.inputVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.fastCheckBox.connect('toggled(bool)', self.updateParameterNodeFromGUI)
        self.ui.taskComboBox.currentTextChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.outputSegmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.outputStatisticsSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.outputRadiomicsSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)

        # Buttons
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
        self.ui.taskComboBox.setCurrentText(self._parameterNode.GetParameter("Task"))
        self.ui.fastCheckBox.checked = self._parameterNode.GetParameter("Fast") == "true"
        self.ui.outputSegmentationSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputSegmentation"))
        self.ui.outputStatisticsSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputStatistics"))
        self.ui.outputRadiomicsSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputRadiomics"))

        # Update buttons states and tooltips
        inputVolume = self._parameterNode.GetNodeReference("InputVolume")
        if inputVolume and self._parameterNode.GetNodeReference("OutputSegmentation"):
            self.ui.applyButton.toolTip = "Start segmentation"
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = "Select input volume and output segmentation"
            self.ui.applyButton.enabled = False

        if inputVolume:
            self.ui.outputSegmentationSelector.baseName = inputVolume.GetName() + " segmentation"
            self.ui.outputStatisticsSelector.baseName = inputVolume.GetName() + " statistics"
            self.ui.outputRadiomicsSelector.baseName = inputVolume.GetName() + " radiomics"

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
        self._parameterNode.SetParameter("Task", self.ui.taskComboBox.currentText)
        self._parameterNode.SetParameter("Fast", "true" if self.ui.fastCheckBox.checked else "false")
        self._parameterNode.SetNodeReferenceID("OutputSegmentation", self.ui.outputSegmentationSelector.currentNodeID)
        self._parameterNode.SetNodeReferenceID("OutputStatistics", self.ui.outputStatisticsSelector.currentNodeID)
        self._parameterNode.SetNodeReferenceID("OutputRadiomics", self.ui.outputRadiomicsSelector.currentNodeID)

        self._parameterNode.EndModify(wasModified)

    def onApplyButton(self):
        """
        Run processing when user clicks "Apply" button.
        """
        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

            self.logic.setupPythonRequirements()

            # Compute output
            self.logic.process(self.ui.inputVolumeSelector.currentNode(), self.ui.outputSegmentationSelector.currentNode(),
                self.ui.fastCheckBox.checked, self.ui.taskComboBox.currentText,
                self.ui.outputStatisticsSelector.currentNode(), self.ui.outputRadiomicsSelector.currentNode())

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
        ScriptedLoadableModuleLogic.__init__(self)

        self.tasks = [
            "total",
            "lung_vessels",
            "cerebral_bleed",
            "hip_implant",
            "coronary_arteries"
        ]

        self.rightLungColor = (0.5, 0.68, 0.5)
        self.leftLungColor = (0.95, 0.84, 0.57)

        self.rightUpperLobeColor = (177./255., 122./255., 101./255. )
        self.rightMiddleLobeColor = (111./255., 184./255., 210./255.)
        self.rightLowerLobeColor = (216./255., 101./255., 79./255.)
        self.leftUpperLobeColor = (128./255., 174./255., 128./255.)
        self.leftLowerLobeColor = (241./255., 214./255., 145./255.)

        self.ribColor = (0.95, 0.84, 0.57)
        self.vesselMaskColor = (0.85, 0.40, 0.31)
        self.pulmonaryArteryColor = (0., 0.59, 0.81)
        self.pulmonaryVeinColor = (0.85, 0.40, 0.31)
        self.tracheaColor = (0.71, 0.89, 1.0)
        self.vesselmaskColor = (216./255., 160./255., 160./255.)
        self.PAColor = (0., 151./255., 206./255.)
        self.PVColor = (216./255., 101./255., 79./255.)
        self.tumorColor = (253./255., 135./255., 192./255.)
        self.thoracicCavityColor = (177./255., 122./255., 101./255.)
        self.unknownColor = (0.39, 0.39, 0.5)


    def log(self, msg):
      slicer.util.showStatusMessage(msg)
      slicer.app.processEvents()

    def setupPythonRequirements(self, upgrade=False):

        # Install PyTorch
        try:
          import PyTorchUtils
        except ModuleNotFoundError as e:
          raise RuntimeError("This module requires PyTorch extension. Install it from the Extensions Manager.")

        torchLogic = PyTorchUtils.PyTorchUtilsLogic()
        if not torchLogic.torchInstalled():
            logging.info('PyTorch module not found')
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
            slicer.util.pip_install("matplotlib")

        # Install AI segmenter
        needToInstallSegmenter = False
        try:
            import totalsegmentator
        except ModuleNotFoundError as e:
            needToInstallSegmenter = True
        if needToInstallSegmenter:
            slicer.util.pip_install("git+https://github.com/wasserth/TotalSegmentator.git")
        elif upgrade:
            slicer.util.pip_install("--upgrade git+https://github.com/wasserth/TotalSegmentator.git")

    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        if not parameterNode.GetParameter("Device"):
            parameterNode.SetParameter("Device", "auto")

    def process(self, inputVolume, outputSegmentation, fast=True, task=None, outputStatistics=None, outputRadiomics=None, segments=None):

        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param inputVolume: volume to be thresholded
        :param outputVolume: thresholding result
        :param fast: faster and less accurate output
        :param task: one of self.tasks, default is "total"
        :param segments: list of segment names, if none then all will be retrieved
        """

        if not inputVolume:
            raise ValueError("Input or output volume is invalid")

        import time
        startTime = time.time()
        logging.info('Processing started')

        # Create new empty folder
        tempFolder = slicer.util.tempDirectory()

        input_file = tempFolder+"/total-segmentator-input.nii"
        output_segmentation_file = tempFolder+"/total-segmentator-output.nii"
        output_segmentation_dir = tempFolder+"/segmentation"
        output_statistics_file = output_segmentation_dir+"/statistics.json"
        output_radiomics_file = output_segmentation_dir+"/statistics_radiomics.json"

        # to reduce computation time when no GPU is available (can still take 5-10 minutes).
        if not fast and device == 'cpu':
            if slicer.util.confirmYesNoDisplay("No GPU is detected. Enable 'fast' mode?"):
                fast = True

        import torch
        if not fast and torch.cuda.get_device_properties(device).total_memory < 7000000000:
            if slicer.util.confirmYesNoDisplay("You have less than 7 GB of GPU memory available. Enable the 'fast' mode?"):
                fast = True

        # Get TotalSegmentator launch script path
        import sysconfig
        totalSegmentatorPath = os.path.join(sysconfig.get_path('scripts'), "TotalSegmentator")
        # Get Python executable path
        import shutil
        pythonSlicerExecutablePath = shutil.which('PythonSlicer')
        if not pythonSlicerExecutablePath:
            raise RuntimeError("Python was not found")
        # Create launcher command
        totalSegmentatorCommand = [ pythonSlicerExecutablePath, totalSegmentatorPath]

        options = []
        if fast:
            options.append("--fast")
        if outputStatistics:
            options.append("--statistics")
        if outputRadiomics:
            options.append("--radiomics")
        if task:
            options.extend(["--task", task])

        # Write input volume to file
        # TotalSegmentator requires NIFTI
        self.log(f"Writing input file to {input_file}")
        volumeStorageNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLVolumeArchetypeStorageNode")
        volumeStorageNode.SetFileName(input_file)
        volumeStorageNode.UseCompressionOff()
        volumeStorageNode.WriteData(inputVolume)
        volumeStorageNode.UnRegister(None)
        logging.info(f"Input volume written to {input_file}")

        # Create multi-file segmentation
        self.log('Creating segmentations with TotalSegmentator AI... (multi-file)')
        paths = ["-i", input_file, "-o", output_segmentation_dir]
        logging.info(f"Total segmentator arguments: {options+paths}")
        proc = slicer.util.launchConsoleProcess(totalSegmentatorCommand + options + paths)
        slicer.util.logProcessOutput(proc)
        # Load result
        self.log('Importing segmentation results... (multi-file)')
        self.loadSegmentationFolder(outputSegmentation, output_segmentation_dir, task)

        # Create single-file segmentation
        self.log('Creating segmentations with TotalSegmentator AI... (single-file)')
        paths = ["-i", input_file, "-o", output_segmentation_file]
        logging.info(f"Total segmentator arguments: {options+paths}")
        proc = slicer.util.launchConsoleProcess(totalSegmentatorCommand + options + paths + ["--ml"])
        slicer.util.logProcessOutput(proc)
        # Load result
        self.log('Importing segmentation results... (single-file)')
        self.loadSegmentation(outputSegmentation, output_segmentation_file, task)

        if outputStatistics:
            self.readStatisticsFile(outputStatistics, output_statistics_file)
        if outputRadiomics:
            self.readStatisticsFile(outputRadiomics, output_radiomics_file)

        # # restore to previous directory state
        # os.chdir(beforeDir)
        logging.info("Segmentation done.")


        # # Read results from output files

        # if outputSegmentation:
        #     segmentationStorageNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSegmentationStorageNode")
        #     segmentationStorageNode.SetFileName(output_segmentation_file)
        #     segmentationStorageNode.ReadData(outputSegmentation)
        #     segmentationStorageNode.UnRegister(None)

        #     # Set segment terminology
        #     segmentId = outputSegmentation.GetSegmentation().GetNthSegmentID(0)
        #     segment = outputSegmentation.GetSegmentation().GetSegment(segmentId)
        #     segment.SetTag(segment.GetTerminologyEntryTagName(),
        #       "Segmentation category and type - 3D Slicer General Anatomy list"
        #       "~SCT^123037004^Anatomical Structure"
        #       "~SCT^12738006^Brain"
        #       "~^^"
        #       "~Anatomic codes - DICOM master list"
        #       "~^^"
        #       "~^^")
        #     segment.SetName("brain")
        #     segment.SetColor(0.9803921568627451, 0.9803921568627451, 0.8823529411764706)

        stopTime = time.time()
        logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')

    def loadSegmentationFolder(self, outputSegmentation, output_segmentation_dir, task):
        """This is just for test.
        The method is very slow, so most likely this method will be removed
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
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelmapVolumeNode, outputSegmentation)

            # sourceSegmentId = outputSegmentation.GetSegmentation().GetSegmentIdBySegmentName(segmentName)
            # if sourceSegmentId:
            #     randomColorsNode.GetColor(labelValue,rgba)
            #     outputSegmentation.GetSegmentation().GetSegment(sourceSegmentId).SetColor(rgba[0], rgba[1], rgba[2])
            #     self.setTerminology(outputSegmentation, segmentName, sourceSegmentId)

            slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

    def loadSegmentation(self, outputSegmentation, output_segmentation_file, task):

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
            colorTableNode.SetColorName(labelValue, labelValueToSegmentName[labelValue])
            randomColorsNode.GetColor(labelValue,rgba)
            colorTableNode.SetColor(labelValue, rgba[0], rgba[1], rgba[2], rgba[3])
        slicer.mrmlScene.AddNode(colorTableNode)

        # Load the segmentation
        segmentationNode = slicer.util.loadSegmentation(output_segmentation_file, {"colorNodeID": colorTableNode.GetID()})
        return segmentationNode

    def readStatisticsFile(self, node, filepath):
        node.SetForceCreateStorageNode()
        node.AddDefaultStorageNode()
        storageNode = node.GetStorageNode()
        storageNode.SetFileName(filepath)
        storageNode.ReadData(node)

    def setTerminology(self, _outputsegmentation, _name, _segID):
        segment = _outputsegmentation.GetSegmentation().GetSegment(_segID)
        if _name == "right lung":
            segment.SetTag(segment.GetTerminologyEntryTagName(),
                "Segmentation category and type - 3D Slicer General Anatomy list"
                "~SCT^123037004^Anatomical Structure"
                "~SCT^39607008^Lung"
                "~SCT^24028007^Right"
                "~Anatomic codes - DICOM master list"
                "~^^"
                "~^^")
        elif _name == "left lung":
            segment.SetTag(segment.GetTerminologyEntryTagName(),
                "Segmentation category and type - 3D Slicer General Anatomy list"
                "~SCT^123037004^Anatomical Structure"
                "~SCT^39607008^Lung"
                "~SCT^7771000^Left"
                "~Anatomic codes - DICOM master list"
                "~^^"
                "~^^")
        elif _name == "left upper lobe":
            segment.SetTag(segment.GetTerminologyEntryTagName(),
                "Segmentation category and type - 3D Slicer General Anatomy list"
                "~SCT^123037004^Anatomical Structure"
                "~SCT^45653009^Upper lobe of Lung"
                "~SCT^7771000^Left"
                "~Anatomic codes - DICOM master list"
                "~^^"
                "~^^")
        elif _name == "left lower lobe":
            segment.SetTag(segment.GetTerminologyEntryTagName(),
                "Segmentation category and type - 3D Slicer General Anatomy list"
                "~SCT^123037004^Anatomical Structure"
                "~SCT^90572001^Lower lobe of lung"
                "~SCT^7771000^Left"
                "~Anatomic codes - DICOM master list"
                "~^^"
                "~^^")
        elif _name == "right upper lobe":
            segment.SetTag(segment.GetTerminologyEntryTagName(),
                "Segmentation category and type - 3D Slicer General Anatomy list"
                "~SCT^123037004^Anatomical Structure"
                "~SCT^45653009^Upper lobe of lung"
                "~SCT^24028007^Right"
                "~Anatomic codes - DICOM master list"
                "~^^"
                "~^^")
        elif _name == "right middle lobe":
            segment.SetTag(segment.GetTerminologyEntryTagName(),
                "Segmentation category and type - 3D Slicer General Anatomy list"
                "~SCT^123037004^Anatomical Structure"
                "~SCT^72481006^Middle lobe of lung"
                "~SCT^24028007^Right"
                "~Anatomic codes - DICOM master list"
                "~^^"
                "~^^")
        elif _name == "right lower lobe":
            segment.SetTag(segment.GetTerminologyEntryTagName(),
                "Segmentation category and type - 3D Slicer General Anatomy list"
                "~SCT^123037004^Anatomical Structure"
                "~SCT^90572001^Lower lobe of lung"
                "~SCT^24028007^Right"
                "~Anatomic codes - DICOM master list"
                "~^^"
                "~^^")
        elif _name == "airways":
            segment.SetTag(segment.GetTerminologyEntryTagName(),
              "Segmentation category and type - 3D Slicer General Anatomy list"
              "~SCT^123037004^Anatomical Structure"
              "~SCT^44567001^Trachea"
              "~^^"
              "~Anatomic codes - DICOM master list"
              "~^^"
              "~^^")
        #else:
        #    print(_name + " not handled during SetTag.")


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
        inputVolume = SampleData.downloadSample('MRBrainTumor1')
        self.delayDisplay('Loaded test data set')

        outputVolume = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLScalarVolumeNode')
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
            logic.process(inputVolume, outputVolume, outputSegmentation)

            slicer.util.setSliceViewerLayers(background=outputVolume)

        else:
            logging.warning("test_TotalSegmentator1 logic testing was skipped")

        self.delayDisplay('Test passed')
