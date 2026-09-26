import os
import zipfile

VERSION = "1.0.0"

MANIFEST_TEMPLATE = """schema_version = "1.0.0"
id = "ingetrazo_sync"
version = "{version}"
name = "IngeTrazo Sync"
tagline = "Live two-way synchronization between Blender and IngeTrazo"
maintainer = "gokuldc"
type = "add-on"
website = "https://github.com/gokuldc/IngeTrazo-blender-sync"
blender_version_min = "4.2.0"
license = ["SPDX:GPL-3.0-or-later"]
tags = ["Import-Export", "3D View"]

[permissions]
network = "Required to connect to the IngeTrazo TCP sync server"
"""

def main():
    if not os.path.exists("dist"):
        os.mkdir("dist")

    # 1. Build Blender Extension (Blender 4.2+ compatible)
    blender_zip_path = f"dist/ingetrazo-blender-sync_blender_v{VERSION}.zip"
    with zipfile.ZipFile(blender_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Write the required manifest for extensions.blender.org
        manifest_content = MANIFEST_TEMPLATE.format(version=VERSION)
        zf.writestr("blender_manifest.toml", manifest_content)
        
        # Write addon script as __init__.py so Blender recognizes it as the extension entry point
        zf.write("blender_addon/ingetrazo_sync.py", arcname="__init__.py")
    
    print(f"[BUILD] Created {blender_zip_path}")

    # 2. Build IngeTrazo Plugin
    ingetrazo_zip_path = f"dist/ingetrazo-blender-sync_ingetrazo_v{VERSION}.zip"
    with zipfile.ZipFile(ingetrazo_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Package the IngeTrazo plugin
        zf.write("ingetrazo_plugin/blender_sync.py", arcname="blender_sync.py")
    
    print(f"[BUILD] Created {ingetrazo_zip_path}")
    print("[BUILD] Build complete! You can upload the .zip files in the 'dist' folder to GitHub Releases.")

if __name__ == "__main__":
    main()
