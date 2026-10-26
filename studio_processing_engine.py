"""Pure image-processing implementation, usable built-in or package-local."""
from chroma_key import remove_chroma_key_with_rim_cleanup, measure_chroma_background
from chroma_profile import PROFILE_VERSION
from studio_processing_api import ProcessingEngine


def create_engine():
    return ProcessingEngine(PROFILE_VERSION, remove_chroma_key_with_rim_cleanup,
                            measure_chroma_background,
                            subject_profiles=("opaque_clipart", "legacy"))
