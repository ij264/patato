#  Copyright (c) Thomas Else 2023.
#  License: BSD-3

from typing import Tuple, Optional, List, Union

import numpy as np

from ..core.image_structures.reconstruction_image import Reconstruction
from ..core.image_structures.single_image import SingleImage
from ..core.image_structures.single_parameter_data import SingleParameterData
from ..core.image_structures.unmixed_image import UnmixedData
from ..io.attribute_tags import UnmixingAttributeTags, GCAttributeTags
from ..io.msot_data import PAData, HDF5Tags
from ..processing.processing_algorithm import SpatialProcessingAlgorithm, ProcessingResult
from ..processing.spectra import Spectrum, SPECTRA_NAMES
from ..utils.time_series_analysis import find_gc_boundaries


class SpectralUnmixer(SpatialProcessingAlgorithm):
    """

    """
    @staticmethod
    def re_grid(reconstruction: np.ndarray, scaling_factor: int):
        """

        Parameters
        ----------
        reconstruction
        scaling_factor

        Returns
        -------

        """
        if scaling_factor == 1:
            return reconstruction
        else:
            n_spatial = 3 if reconstruction.ndim == 5 else 2
            reshape_kernel_size = tuple(min(scaling_factor, size) for size in reconstruction.shape[-n_spatial:])
            extend = (None,) * len(reconstruction.shape[:-n_spatial])
            kernel = np.ones(reshape_kernel_size)[extend]
            kernel /= np.sum(kernel)
            from scipy.signal import convolve
            smoothed = convolve(reconstruction, kernel, mode="same")
            slice_selection = (slice(None, None),) * len(reconstruction.shape[:-n_spatial])
            slice_selection += (slice(None, None, scaling_factor),) * n_spatial
            return smoothed[slice_selection]

    def run(self, reconstruction: Reconstruction, _, **kwargs) -> Tuple[UnmixedData, dict, None]:
        # Select the right wavelengths:
        wavelengths = self.wavelengths
        wavelength_indices = np.where(np.isclose(reconstruction.wavelengths[:, None], wavelengths[None, :]))[0]

        # Get the reconstructed data
        recon_data = reconstruction[:, wavelength_indices].raw_data

        # Change the grid
        recon_data = self.re_grid(recon_data, self.rescaling_factor)

        # Unmix.
        unmixed = np.einsum('ij...,jk->ik...', recon_data, self.pseudo_inverse)

        output_data = UnmixedData(unmixed, self.chromophore_names,
                                  algorithm_id=self.algorithm_id,
                                  attributes=reconstruction.attributes,
                                  field_of_view=reconstruction.fov_3d)
        for a in reconstruction.attributes:
            output_data.attributes[a] = reconstruction.attributes[a]
        output_data.attributes[UnmixingAttributeTags.SUFFIX] = self.algorithm_id
        output_data.attributes[UnmixingAttributeTags.UNMIXING_WAVELENGTHS] = wavelengths
        output_data.attributes[UnmixingAttributeTags.SPECTRA] = self.chromophore_names
        output_data.hdf5_sub_name = reconstruction.hdf5_sub_name
        return output_data, {}, None

    def __init__(self, chromophores: List[Union[Spectrum, str]], wavelengths,
                 rescaling_factor=1, algorithm_id=""):
        super().__init__(algorithm_id)
        for i, c in enumerate(chromophores):
            if type(c) == str:
                chromophores[i] = SPECTRA_NAMES[c]
        spectra = np.array([c.get_spectrum(wavelengths) for c in chromophores])
        spectra = np.atleast_2d(spectra)
        self.chromophore_names = np.array([c.get_name() for c in chromophores])
        self.forward_matrix = spectra
        self.pseudo_inverse = np.linalg.pinv(spectra)
        self.wavelengths = np.array(wavelengths)
        self.rescaling_factor = rescaling_factor


class SO2Calculator(SpatialProcessingAlgorithm):
    def run(self, spatial_data: UnmixedData, _, **kwargs):
        hb_axis = np.where(spatial_data.spectra == "Hb")[0][0]
        hbo2_axis = np.where(spatial_data.spectra == "HbO2")[0][0]
        thb = spatial_data.raw_data[:, hb_axis] + spatial_data.raw_data[:, hbo2_axis]
        thb[thb == 0] = np.nan # Just so it can pass tests.
        so2 = spatial_data.raw_data[:, hbo2_axis] / thb
        so2 = so2[:, None]
        output_data = SingleParameterData(so2, ["so2"],
                                          algorithm_id=self.algorithm_id,
                                          attributes=spatial_data.attributes,
                                          field_of_view=spatial_data.fov_3d)
        for a in spatial_data.attributes:
            output_data.attributes[a] = spatial_data.attributes[a]
        output_data.hdf5_sub_name = spatial_data.hdf5_sub_name
        return output_data, {}, None


class THbCalculator(SpatialProcessingAlgorithm):
    def run(self, spatial_data: UnmixedData, _, **kwargs):
        hb_axis = np.where(spatial_data.spectra == "Hb")[0][0]
        hbo2_axis = np.where(spatial_data.spectra == "HbO2")[0][0]
        thb = spatial_data.raw_data[:, hb_axis] + spatial_data.raw_data[:, hbo2_axis]
        thb = thb[:, None]
        output_data = SingleParameterData(thb, ["thb"],
                                          algorithm_id=self.algorithm_id,
                                          attributes=spatial_data.attributes,
                                          field_of_view=spatial_data.fov_3d)
        for a in spatial_data.attributes:
            output_data.attributes[a] = spatial_data.attributes[a]
        output_data.hdf5_sub_name = spatial_data.hdf5_sub_name
        return output_data, {}, None


class GasChallengeAnalyser(SpatialProcessingAlgorithm):
    def __init__(self, smoothing_window_size=10,
                 display_output=True, smoothing_sigma=2,
                 start_skip=0, challenge_type=1, buffer_width=5):
        super().__init__()
        self.smoothing_window_size = smoothing_window_size
        self.display = display_output
        self.smoothing_sigma = smoothing_sigma
        self.start_skip = start_skip
        self.sign = challenge_type
        self.buffer = buffer_width

    def run(self, so2: SingleParameterData, pa_data: PAData, **kwargs) -> Optional[Tuple[SingleImage, dict,
                                                                                         Optional[List[
                                                                                             ProcessingResult]]]]:
        rois = pa_data.get_rois()
        if not rois:
            raise RuntimeError("No reference region available.")
        elif ("reference_", "0") not in rois:
            raise RuntimeError("No reference region available.")

        roi_mask, _ = rois[("reference_", "0")].to_mask_slice(so2)
        steps = find_gc_boundaries(roi_mask, so2, self.smoothing_window_size,
                                   self.display, self.smoothing_sigma, self.start_skip,
                                   self.sign)
        if self.display:
            if input("Continue with analysis? ") not in ["Y", "y"]:
                if input("Set Manually? ") not in ["Y", "y"]:
                    return None
                else:
                    run = int(input("Enter Changeover Run Number: "))
                    steps[1] = run
                    steps = [steps[0], steps[1], steps[-1]]
                    print(steps)
        so2_measurements = so2.raw_data[:, 0]
        baseline_region = so2_measurements[steps[0]: steps[1] - self.buffer]
        baseline_so2 = np.mean(baseline_region, axis=0)
        baseline_so2_std = np.std(baseline_region, axis=0)
        post_so2 = so2_measurements[steps[1] + self.buffer: steps[2] - self.buffer]
        delta_so2 = np.mean(post_so2, axis=0) - baseline_so2

        delta_output = SingleImage(delta_so2, [HDF5Tags.DELTA_SO2],
                                   attributes=so2.attributes,
                                   field_of_view=so2.fov_3d)
        delta_output.hdf5_sub_name = so2.hdf5_sub_name
        delta_output.attributes[GCAttributeTags.STEPS] = steps
        delta_output.attributes[GCAttributeTags.BUFFER] = self.buffer
        delta_output.attributes[GCAttributeTags.SKIP_START] = self.start_skip
        baseline_so2_output = SingleImage(baseline_so2, [HDF5Tags.BASELINE_SO2], attributes=delta_output.attributes)
        baseline_so2_output.hdf5_sub_name = so2.hdf5_sub_name
        baseline_so2_sigma_output = SingleImage(baseline_so2_std, [HDF5Tags.BASELINE_SO2_STANDARD_DEVIATION],
                                                attributes=delta_output.attributes)
        baseline_so2_sigma_output.hdf5_sub_name = so2.hdf5_sub_name
        return delta_output, {}, [baseline_so2_output, baseline_so2_sigma_output]


def find_dce_boundaries(roi_mask, icg, smoothing_window_size, display, smoothing_sigma):
    return find_gc_boundaries(roi_mask, icg, smoothing_window_size,
                              display, smoothing_sigma, 0, 2)


class DCEAnalyser(SpatialProcessingAlgorithm):
    def __init__(self, smoothing_window_size=10,
                 display_output=True, smoothing_sigma=2,
                 buffer_width=5, unmix_index=2):
        super().__init__()
        self.smoothing_window_size = smoothing_window_size
        self.display = display_output
        self.smoothing_sigma = smoothing_sigma
        self.buffer = buffer_width
        self.unmix_index = unmix_index

    def run(self, unmixed_data: SingleParameterData, pa_data: PAData, **kwargs) -> Optional[Tuple[SingleImage, dict,
                                                                                                  Optional[List[
                                                                                                      ProcessingResult]]]]:
        rois = pa_data.get_rois()
        if not rois:
            raise RuntimeError("No reference region available.")
        elif ("reference_", "0") not in rois:
            raise RuntimeError("No reference region available.")
        icg = unmixed_data[:, self.unmix_index]

        roi_mask, _ = rois[("reference_", "0")].to_mask_slice(icg)

        steps = find_dce_boundaries(roi_mask, icg, self.smoothing_window_size,
                                    self.display, self.smoothing_sigma)

        if self.display:
            if input("Continue with analysis? ") not in ["Y", "y"]:
                if input("Set Manually? ") not in ["Y", "y"]:
                    return None
                else:
                    run = int(input("Enter Changeover Run Number: "))
                    steps[1] = run
                    steps = [steps[0], steps[1], steps[-1]]
                    print(steps)

        icg_measurements = icg.raw_data
        baseline_region = icg_measurements[steps[0]: steps[1] - self.buffer]
        baseline_icg = np.mean(baseline_region, axis=0)
        baseline_icg_std = np.std(baseline_region, axis=0)
        post_icg = icg_measurements[steps[1]: steps[2] - self.buffer]
        delta_icg = np.max(post_icg, axis=0) - baseline_icg

        delta_output = SingleImage(delta_icg, [HDF5Tags.DELTA_ICG],
                                   attributes=icg.attributes,
                                   field_of_view=icg.fov_3d)
        delta_output.hdf5_sub_name = icg.hdf5_sub_name
        delta_output.attributes[GCAttributeTags.STEPS] = steps
        delta_output.attributes[GCAttributeTags.BUFFER] = self.buffer
        baseline_icg_output = SingleImage(baseline_icg, [HDF5Tags.BASELINE_ICG],
                                          attributes=delta_output.attributes,
                                          field_of_view=icg.fov_3d)
        baseline_icg_output.hdf5_sub_name = icg.hdf5_sub_name
        baseline_icg_sigma_output = SingleImage(baseline_icg_std, [HDF5Tags.BASELINE_ICG_SIGMA],
                                                attributes=delta_output.attributes,
                                                field_of_view=icg.fov_3d)
        baseline_icg_sigma_output.hdf5_sub_name = icg.hdf5_sub_name
        return delta_output, {}, [baseline_icg_output, baseline_icg_sigma_output]
