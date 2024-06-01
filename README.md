# TotalSegmentator

3D Slicer extension for fully automatic whole body CT segmentation using ["TotalSegmentator" AI model](https://github.com/wasserth/TotalSegmentator). Computation time is less than one minute.

![](Screenshot01.jpg)

If you use the TotalSegmentator nn-Unet function from this software in your research, please cite:

> Wasserthal J., Meyer M., , Hanns-Christian Breit H.C., Cyriac J., Shan Y., Segeroth, M.: TotalSegmentator: robust segmentation of 104 anatomical structures in CT images. https://arxiv.org/abs/2208.05868

## Setup

1. Setup your GPU driver (optional)

If you have a powerful GPU is available then a full-quality segmentation can be computed in a few minutes, instead of 40-50 minutes on the CPU. Therefore, it is recommended to set up GPU acceleration as described in this section.

- If a strong GPU with 7GB or more memory is available:
  - On Windows:
    - If using NVIDIA GPU: Make sure CUDA is installed. [CUDA version must be one of those listed on pytorch website as "Compute platform" for your system](https://pytorch.org/get-started/locally/). You can download CUDA from [here](https://developer.nvidia.com/cuda-downloads).
    - PyTorch does not officially support AMD GPUs for on Windows, therefore you need to use the CPU.
  - On Linux:
    - If using NVIDIA GPU: Make sure NVIDIA drivers are installed. If CUDA is installed then make sure [CUDA version is one of those listed on pytorch website as "Compute platform" for your system](https://pytorch.org/get-started/locally/). If CUDA is not installed then it will be set up automatically during installation (pytorch binary packages contain the appropriate CUDA version).
    - If using AMD GPU: In theory, ROCm-compatible AMD GPUs should work, but this is not tested.
  - On macOS: PyTorch does not officially support GPUs for macOS, therefore you need to use the CPU.
- If suitable GPU is not available: Graphics driver updates or CUDA installation is not necessary, everything will still work, it will just take more time.

2. Install latest version of [3D Slicer](https://slicer.readthedocs.io/en/latest/user_guide/getting_started.html#installing-3d-slicer)

3. [Install `TotalSegmentator` extension in 3D Slicer](https://slicer.readthedocs.io/en/latest/user_guide/extensions_manager.html#install-extensions)

## Tutorial

- Start 3D Slicer
- Go to `Sample Data` module and load `CTA Abdomen (Panoramix)` data set
- Go to `TotalSegmentator` module
- Select `Input volume` -> `Panoramix-cropped`
- Select `Segmentation` -> `Create new segmentation`
- Click `Apply`
  - When this module is used the first time:
    - It needs to download and install PyTorch and TotalSegmentator Python packages and weights for the AI models. This can take 5-10 minutes and several GB disk space.
    - You may get an error popup: `Failed to compute results ... Command ... 'pip', 'install' ... returned non-zero exit status 1`. This may be normal, see what to do in [Troubleshooting section](#failed-to-compute-results-error-at-the-first-run)
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
  - Use latest development version: use latest development version from TotalSegmentator master branch during a forced reinstall. 
  - Force reinstall: force reinstallation of the AI engine - TotalSegmentator Python package. This may be needed if other modules compromise the installation.
  - Import weights: When using TotalSegmentator, weights are often downloaded automatically. You can import any specialized or licensed weights you receive from the developer so that TotalSegmentator can find and use them.  
  - Get TotalSegmentator package information: retrieve installed version of the AI engine - TotalSegmentator Python package.

## Troubleshooting

### Failed to compute results error at the first run

#### Problem: Error popup on the first run: `Failed to compute results ... Command ... 'pip', 'install' ... returned non-zero exit status 1`

Explanation: This happens because when TotalSegmentator is run for the first time, it needs to download and install PyTorch and TotalSegmentator Python packages. Since the application may have already loaded different versions of these packages, the packages need to be uninstalled first. This uninstallation may fail because some packages may be already in use. Restarting the application unloads these modules so they are no longer in use. Therefore after a restart, TotalSegmentator will be able to install all the necessary packages.

Solution: Restart Slicer and run TotalSegmentator module again.

#### Problem: Error popup on the first run: `Failed to compute results ... Command ... 'PythonSlicer', TotalSegmentator.exe ... returned non-zero exit status 120`

Explanation: This typically happens when PyTorch is not installed correctly or your computer runs out of memory.

Solution:
- Check the message log (textbox under the Apply button). If you see a message like `RuntimeError: ... DefaultCPUAllocator: not enough memory: you tried to allocate ... bytes.` then it means that your computer has not enough memory to process the input image. You can use `Crop volume` module to crop the your image to the relevant region and/or resample it (with using a scaling factor >1) until the memory usage drops low enough so that your computer can handle it. Alternatively, you can install more physical RAM or configure your operating system to use  more virtual memory.
- If the problem does not seem to be due to running out of memory then reinstall PyTorch as described in solution of `Segmentation fails while predicting` issue.

### Segmentation fails while predicting

Problem: Segmentation fails while predicting and the `RuntimeError: CUDA out of memory.` message is found in the message log (textbox under the Apply button).

Explanation: This means that a CUDA-capable GPU is available, but it is not powerful enough to be used by TotalSegmentator.

Solution: It is recommended to switch to use the CPU by the following steps:
- Go to `PyTorch Util` module, click `Uninstall PyTorch`. An error may be reported at the end of this step, as some PyTorch files are in use. Click `Restart the application` button to unload all PyTorch files.
- Go to `PyTorch Util` module, select `cpu` as `Computation backend`, and click `Install PyTorch`.

If your GPU has more than 7GB memory and you still get this error then the error message might indicate that the PyTorch CUDA version does not match the CUDA version installed on the system. Reinstall PyTorch with the correct CUDA version by following the instructions given below for [GPU is not found](#gpu-is-not-found).

### GPU is not found

Problem: Your computer has a CUDA-capable GPU but TotalSegmentator reports that GPU is not available.

Explanation: CUDA may not be installed on the system or CUDA version in PyTorch does not match the system CUDA version.

Solution:
- Make sure that the the CUDA vesion installed on the system [is one of those listed on pytorch website as "Compute platform" for your system](https://pytorch.org/get-started/locally/). You can download CUDA from [here](https://developer.nvidia.com/cuda-downloads).
- Go to `PyTorch Util` module, click `Uninstall PyTorch`. An error may be reported at the end of this step, as some PyTorch files are in use. Click `Restart the application` button to unload all PyTorch files.
- Go to `PyTorch Util` module, select the `Computation backend` that matches the system CUDA version, and click `Install PyTorch`. The CUDA computational backend name has the format `cuNNN`, where _NNN_ corresponds to the CUDA major+minor version. For example, CUDA 11.7 backend name is `cu117`.

### Face segment is inaccurate

Problem: There is a big segment called `face` at the front of the head, which is not an accurate segmentation of the face.

Explanation: This segment is not designed to match the shape of an anatomical feature, but it designates the general area of the face. It can be used to remove features (for example by masking or blurring the image or clipping models) that might otherwise identify the individual subject. Removing these features makes it easier to share 3D data.

### Fail to download model files

Model files are hosted on github.com or Zenodo.org and downloaded automatically when segmenting the first time. Institutional firewall or proxy servers may prevent access or the server may be temporarily overloaded, which may cause an error report similar to `requests.exceptions.HTTPError: 404 Client Error: Not Found for url: https://zenodo.org/record/6802052/files/Task256_TotalSegmentator_3mm_1139subj.zip?download=1`. Potential solutions:
- retry later when the server may be less overloaded
- talk to IT administrators or use a VPN to access the server
- download the file manually and unzip it in the `.totalsegmentator` folder in the user's profile (for example in `c:\Users\(yourusername)\.totalsegmentator\nnunet\results\Dataset291_TotalSegmentator_part1_organs_1559subj`)

## Contributing

Contributions to this extensions are welcome. Please send a pull request with any suggested changes. [3D Slicer contribution guidelines](https://github.com/Slicer/Slicer/blob/main/CONTRIBUTING.md) apply.

## Contact

Please post any questions to the [Slicer Forum](https://discourse.slicer.org).

Developers of this extension are not associated with the developers of TotalSegmentator, just provide the convenient 3D Slicer based user interface.
