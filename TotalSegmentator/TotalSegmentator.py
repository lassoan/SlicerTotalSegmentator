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
        if inputVolume:
            self.ui.applyButton.toolTip = "Start segmentation"
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = "Select input volume"
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

            # Compute output
            self.logic.process(self.ui.inputVolumeSelector.currentNode(), self.ui.outputSegmentationSelector.currentNode(),
                self.ui.fastCheckBox.checked, self.ui.taskComboBox.currentText,
                self.ui.outputStatisticsSelector.currentNode(), self.ui.outputRadiomicsSelector.currentNode())

        self.ui.statusLabel.appendPlainText("\nProcessing finished.")
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

        self.logCallback = None
        self.clearOutputFolder = True

        self.tasks = [
            "total",
            "lung_vessels",
            "cerebral_bleed",
            "hip_implant",
            "coronary_arteries"
        ]

    def log(self, text):
        logging.info(text)
        if self.logCallback:
            self.logCallback(text)

    def setupPythonRequirements(self, upgrade=False):

        # Install PyTorch
        try:
          import PyTorchUtils
        except ModuleNotFoundError as e:
          raise RuntimeError("This module requires PyTorch extension. Install it from the Extensions Manager.")

        torchLogic = PyTorchUtils.PyTorchUtilsLogic()
        if not torchLogic.torchInstalled():
            self.log('PyTorch module not found')
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
        if not parameterNode.GetParameter("Fast"):
            parameterNode.SetParameter("Fast", "True")
        if not parameterNode.GetParameter("Task"):
            parameterNode.SetParameter("Task", "total")

    def logProcessOutput(self, proc):
        # Wait for the process to end and forward output to the log
        from subprocess import CalledProcessError
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            self.log(line.rstrip())
        proc.wait()
        retcode = proc.returncode
        if retcode != 0:
            raise CalledProcessError(retcode, proc.args, output=proc.stdout, stderr=proc.stderr)

    def process(self, inputVolume, outputSegmentation, fast=True, task=None, outputStatistics=None, outputRadiomics=None):

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

        import time
        startTime = time.time()
        self.log('Processing started')

        # Create new empty folder
        tempFolder = slicer.util.tempDirectory()

        inputFile = tempFolder+"/total-segmentator-input.nii"
        outputSegmentationFolder = tempFolder + "/segmentation"
        outputSegmentationFile = tempFolder + "/segmentation.nii"
        outputStatisticsFile = outputSegmentationFolder + "/statistics.json"
        outputRadiomicsFile = outputSegmentationFolder + "/statistics_radiomics.json"

        # Recommend the user to switch to fast mode if no GPU or not enough memory is available
        import torch
        if not fast and not torch.has_cuda:
            if slicer.util.confirmYesNoDisplay("No GPU is detected. Enable 'fast' mode to get results in a few ten minutes instead of hours?"):
                fast = True
        if not fast and torch.cuda.get_device_properties(0).total_memory < 7000000000:
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

        # Get options
        options = ["-i", inputFile, "-o", outputSegmentationFolder]
        createSegmentationSubfolder = False
        if outputStatistics:
            options.append("--statistics")
            createSegmentationSubfolder = True
        if outputRadiomics:
            options.append("--radiomics")
            createSegmentationSubfolder = True

        if createSegmentationSubfolder:
            os.mkdir(outputSegmentationFolder)

        # Write input volume to file
        # TotalSegmentator requires NIFTI
        self.log(f"Writing input file to {inputFile}")
        volumeStorageNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLVolumeArchetypeStorageNode")
        volumeStorageNode.SetFileName(inputFile)
        volumeStorageNode.UseCompressionOff()
        volumeStorageNode.WriteData(inputVolume)
        volumeStorageNode.UnRegister(None)

        # Launch in fast mode to get initial segmentation
        if task != "total":
            preOptions = options + ["--fast"]
            self.log('Creating segmentations with TotalSegmentator AI (pre-run)...')
            self.log(f"Total Segmentator arguments: {preOptions}")
            proc = slicer.util.launchConsoleProcess(totalSegmentatorCommand + preOptions)
            self.logProcessOutput(proc)

        # Launch TotalSegmentator
        options.append("--ml")  # multi-label = all labels in a single file
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
        self.readSegmentation(outputSegmentation, outputSegmentationFile, task)

        if outputStatistics:
            self.readStatisticsFile(outputStatistics, outputStatisticsFile)
        if outputRadiomics:
            self.readStatisticsFile(outputRadiomics, outputRadiomicsFile)

        if self.clearOutputFolder:
            self.log("Cleaning up temporary folder...")
            if os.path.isdir(tempFolder):
                shutil.rmtree(tempFolder)

        stopTime = time.time()
        self.log(f'Processing completed in {stopTime-startTime:.2f} seconds')


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

    def readStatisticsFile(self, node, filepath):
        node.SetForceCreateStorageNode(True)
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