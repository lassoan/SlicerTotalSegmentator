# TotalSegmentator

3D Slicer extension for fully automatic whole body CT segmentation using ["TotalSegmentator" AI model](https://github.com/wasserth/TotalSegmentator). Computation time using a CUDA-capable GPU takes 1-2 minutes.

![](Screenshot01.jpg)

If you use the TotalSegmentator nn-Unet function from this software in your research, please cite:

> Wasserthal J., Meyer M., , Hanns-Christian Breit H.C., Cyriac J., Shan Y., Segeroth, M.: TotalSegmentator: robust segmentation of 104 anatomical structures in CT images. https://arxiv.org/abs/2208.05868

## Tutorial

- If you have a CUDA-capable GPU then make sure CUDA is installed to enable faster segmentation (1-2 minutes instead of tens of minutes). You can download CUDA from [here](https://developer.nvidia.com/cuda-downloads).
- Install latest Slicer Preview Release of [3D Slicer](https://slicer.readthedocs.io/en/latest/user_guide/getting_started.html#installing-3d-slicer)
- [Install `TotalSegmentator` extension](https://slicer.readthedocs.io/en/latest/user_guide/extensions_manager.html#install-extensions)
- Start 3D Slicer
- Go to `Sample Data` module and load `CTA Abdomen (Panoramix)` data set
- Go to `TotalSegmentator` module
- Select `Input volume` -> `Panoramix-cropped`
- Select `Segmentation` -> `Create new segmentation`
- Click `Apply`
  - When this module is used the first time, it needs to download and install PyTorch and TotalSegmentator Python packages and weights for the AI models. This can take 5-10 minutes and several GB disk space.
  - If a GPU is available then results are computed within about 20 seconds in fast mode, and 1-2 minutes in normal mode. If computation is done on CPU then it may take up to 5-15 minutes in fast mode.
- To display the segmentation in 3D: go to Data module and drag-and-drop the segmented into the 3D view.

## User interface

- Inputs
  - Input volume: input CT image
  - Segmentation task: instead of the default "total" segmentation, a more specialized segmentation model can be chosen
  - Fast: performs segmentation faster, but with less accuracy
- Outputs
  - Segmentation: it will contain a brain segment, which specifies the brain region

## Contact

Please post any questions to the [Slicer Forum](https://discourse.slicer.org).

Developers of this extension are not associated with the developers of TotalSegmentator, just provide the convenient 3D Slicer based user interface.
