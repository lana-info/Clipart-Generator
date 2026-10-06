"""Stable host contract for the shared, signed image-processing component.

One engine is selected before a job starts. The host owns files, credentials,
authorization and job lifetime; the engine only receives in-memory images.
"""
from dataclasses import dataclass, field
import re
from typing import Callable

from PIL import Image
from studio_module_api import CapabilityRequirement

PROCESSING_COMPONENT_ID = "image-processing"
PROCESSING_CONSUMERS = frozenset({"auto-clipart", "clipart", "processing"})
PROCESSING_CAPABILITY = CapabilityRequirement("studio.image-processing", 1)
_PROFILE = re.compile(r"opaque-clipart-v[1-9][0-9]{0,5}\Z")


class ChromaKeyAmbiguousError(ValueError):
    """The source cannot safely be keyed; manual correction is required."""


class ChromaKeySubjectColorError(ChromaKeyAmbiguousError):
    """Removing the key would erase an enclosed subject detail."""


def valid_processing_profile(value):
    return isinstance(value, str) and _PROFILE.fullmatch(value) is not None


@dataclass(frozen=True)
class ProcessingEngine:
    profile: str
    remove_background: Callable = field(repr=False, compare=False)
    measure_background: Callable = field(repr=False, compare=False)
    api_version: int = 1
    subject_profiles: tuple[str, ...] = ("opaque_clipart",)

    def __post_init__(self):
        if (type(self.api_version) is not int or self.api_version != 1
                or not valid_processing_profile(self.profile)
                or not isinstance(self.subject_profiles, tuple)
                or not self.subject_profiles or "opaque_clipart" not in self.subject_profiles
                or any(value not in ("opaque_clipart", "legacy") for value in self.subject_profiles)
                or not callable(self.remove_background) or not callable(self.measure_background)):
            raise ValueError("Unsupported image-processing contract")

    def remove(self, source: Image.Image, color: str, *, subject_profile: str = "opaque_clipart") -> Image.Image:
        if subject_profile not in self.subject_profiles:
            raise ValueError("Модуль обработки не поддерживает выбранный тип изображения. Обновите модуль обработки.")
        result = self.remove_background(source, color, subject_profile=subject_profile)
        if not isinstance(result, Image.Image) or result.mode != "RGBA" or result.size != source.size:
            raise ValueError("Image-processing component returned an invalid image")
        return result


@dataclass
class ProcessingEngineLease:
    engine: ProcessingEngine
    lease: object = field(default=None, repr=False)

    def close(self, *_args):
        if self.lease is not None:
            self.lease.close()
