"""Git-backed scientific claim management for the GitScience MVP."""

from .repository import GitScienceRepository
from .verification import VerificationError, verify_claim

__all__ = ["GitScienceRepository", "VerificationError", "verify_claim"]
