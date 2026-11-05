"""Run the TotalSegmentator command line interface on the Vulkan device of PyTorch.

TotalSegmentator accepts only the "gpu", "cpu", and "mps" device names, and it does not import torchvulkan,
therefore it cannot use the Vulkan device that the PyTorch extension registers when no CUDA device is available.
The TotalSegmentator Slicer module runs this script in that case: it imports torchvulkan (which registers the
"vulkan" device in PyTorch) and extends the device handling of the TotalSegmentator package with that device.
The installed TotalSegmentator package is not modified.

This script accepts the same command-line arguments as the TotalSegmentator executable.
"""

import totalsegmentator.python_api as python_api

_originalValidateDeviceType = python_api.validate_device_type_api
_originalSelectDevice = python_api.select_device

_vulkanAvailable = False
try:
    import torchvulkan  # registers the "vulkan" device in PyTorch
    _vulkanAvailable = torchvulkan.is_available()
except Exception as error:
    print(f"Vulkan device is not available ({error}), therefore the CPU is used.")


def _validateDeviceType(value):
    if value == "vulkan":
        return value
    return _originalValidateDeviceType(value)


def _selectDevice(device):
    if device == "vulkan":
        if _vulkanAvailable:
            import torch
            return torch.device("vulkan")
        print("No usable Vulkan device was found, therefore the CPU is used. This can be very slow.")
        return "cpu"
    return _originalSelectDevice(device)


python_api.validate_device_type_api = _validateDeviceType
python_api.select_device = _selectDevice

from totalsegmentator.bin.TotalSegmentator import main

if __name__ == "__main__":
    main()
