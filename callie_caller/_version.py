"""
Version management for Callie Caller.
This file is the single source of truth for version information.
"""

__version__ = "1.0.0"
__version_info__ = tuple(map(int, __version__.split('.')))

# Build metadata
__build__ = "production"
__commit__ = "unknown"

# Version components
MAJOR, MINOR, PATCH = __version_info__

def get_version(include_build=False):
    """Get the current version string."""
    version = __version__
    if include_build and __build__ != "production":
        version += f"-{__build__}"
    return version

def get_version_info():
    """Get detailed version information."""
    return {
        "version": __version__,
        "version_info": __version_info__,
        "major": MAJOR,
        "minor": MINOR,
        "patch": PATCH,
        "build": __build__,
        "commit": __commit__
    }

def bump_version(component="patch"):
    """
    Bump version component. Used by build scripts.
    
    Args:
        component: 'major', 'minor', or 'patch'
    """
    global __version__, __version_info__, MAJOR, MINOR, PATCH
    
    if component == "major":
        MAJOR += 1
        MINOR = 0
        PATCH = 0
    elif component == "minor":
        MINOR += 1
        PATCH = 0
    elif component == "patch":
        PATCH += 1
    else:
        raise ValueError(f"Invalid component: {component}")
    
    __version_info__ = (MAJOR, MINOR, PATCH)
    __version__ = f"{MAJOR}.{MINOR}.{PATCH}"
    
    return __version__ 