# TotalSegmentator

3D Slicer extension for fully automatic whole body CT segmentation using ["TotalSegmentator" AI model](https://github.com/wasserth/TotalSegmentator). Computation time is less than one minute.

![](Screenshot01.jpg)

If you use the TotalSegmentator nn-Unet function from this software in your research, please cite:

> Wasserthal J., Meyer M., , Hanns-Christian Breit H.C., Cyriac J., Shan Y., Segeroth, M.: TotalSegmentator: robust segmentation of 104 anatomical structures in CT images. https://arxiv.org/abs/2208.05868

## Setup

1. Setup your GPU driver (optional)

If you have a powerful NVIDIA GPU then a full-quality segmentation can be computed in a few minutes (instead of 40-50 minutes on the CPU). Therefore, it is recommended to set up the correct graphics driver and CUDA version if such GPU is available. Currently, CUDA is not available on macOS.

- If a CUDA-capable GPU with 7GB or more memory is available: Make sure CUDA is installed. [CUDA version must be one of those listed on pytorch website as "Compute platform" for your system](https://pytorch.org/get-started/locally/). You can download CUDA from [here](https://developer.nvidia.com/cuda-downloads).
- If a CUDA-capable GPU is available but it has less than 7GB memory: TotalSegmentator can fail due to running out of memory. To use the CPU for segmentation (and thus allow segmentation to complete slowly, but successfully), you can force usage of the CPU by installing a CPU-only version of pytorch in Slicer. Run this in the Windows terminal: `"%localappdata%\NA-MIC\Slicer 5.2.1\bin\PythonSlicer.exe" -m pip install torch torchvision torchaudio --force-reinstall` . The same command works on linux, as well, just use the correct `PythonSlicer` executable location.
- If CUDA-capable GPU is not available then the everything still works, just takes more time.

2. Install latest version of [3D Slicer](https://slicer.readthedocs.io/en/latest/user_guide/getting_started.html#installing-3d-slicer)

3. [Install `TotalSegmentator` extension in 3D Slicer](https://slicer.readthedocs.io/en/latest/user_guide/extensions_manager.html#install-extensions)

## Tutorial

- Start 3D Slicer
- Go to `Sample Data` module and load `CTA Abdomen (Panoramix)` data set
- Go to `TotalSegmentator` module
- Select `Input volume` -> `Panoramix-cropped`
- Select `Segmentation` -> `Create new segmentation`
- Click `Apply`
  - When this module is used the first time, it needs to download and install PyTorch and TotalSegmentator Python packages and weights for the AI models. This can take 5-10 minutes and several GB disk space. Downloading of TotalSegmentator requires `git` revision control tool. It is often installed already on many computers. If it is not found then you may be asked at this point to install it (`git` can be downloaded from [here](https://git-scm.com/download)).
  - Expected computation time:
    - With CUDA-capable GPU: 20-30 seconds in fast mode, 40-50 seconds in full-resolution mode.
    - Without GPU: 1 minute in fast mode, 40-50 minutes in full-resolution mode.
- To display the segmentation in 3D: click the `Show 3D` button

## User interface

- Inputs
  - Input volume: input CT image
  - Segmentation task: instead of the default "total" segmentation, a more specialized segmentation model can be chosen
  - Fast: performs segmentation faster, but at lower resolution
- Outputs
  - Segmentation: it will contain a brain segment, which specifies the brain region
  - Show 3D: show/hide segments in 3D views
- Advanced:
  - Use standard segment names: use names defined in standard terminology files from [DCMQI](https://github.com/QIICR/dcmqi) (enabled by default). If disabled then TotalSegmentator identifiers will be used as segment names.
  - Upgrade: upgrade the AI engine - TotalSegmentator Python package - to the very latest version from GitHub.
  - Get TotalSegmentator package information: retrieve installed version of the AI engine - TotalSegmentator Python package.

## Troubleshooting

### Segmentation fails while predicting

If segmentation fails while predicting and the `RuntimeError: CUDA out of memory.` message is found in the message log (textbox under the Apply button) then it means that a CUDA-capable GPU is available, but it is not powerful enough to be used by TotalSegmentator.

In this case, it is recommended to switch to use the CPU. The easiest is to install the CPU version of pytorch by exiting Slicer and typing this into the Windows terminal (replace `%localappdata%\NA-MIC\Slicer 5.2.1\bin` by the actual path of `PythonSlicer.exe` if not using Windows or not Slicer 5.2.1):

```txt
"%localappdata%\NA-MIC\Slicer 5.2.1\bin\PythonSlicer.exe" -m pip install torch torchvision torchaudio --force-reinstall
```

We have been discussing in the TotalSegmentator issue tracker how we could avoid this workaround to make switching to CPU easier in case the computer has a GPU but not powerful enough: https://github.com/wasserth/TotalSegmentator/issues/37. Hopefully a more convenient solution will be available soon.

### GPU is not found

[CUDA version must be one of those listed on pytorch website as "Compute platform" for your system](https://pytorch.org/get-started/locally/). You can download CUDA from [here](https://developer.nvidia.com/cuda-downloads). After updating CUDA, pytorch need to be reinstalled. Either uninstall and install Slicer again, or run this command in the Windows terminal to uninstall pytorch (Slicer will reinstall the correct version automatically):

```txt
"%localappdata%\NA-MIC\Slicer 5.2.1\bin\PythonSlicer.exe" -m pip uninstall torch torchvision torchaudio
```

## Contact

Please post any questions to the [Slicer Forum](https://discourse.slicer.org).

Developers of this extension are not associated with the developers of TotalSegmentator, just provide the convenient 3D Slicer based user interface.
