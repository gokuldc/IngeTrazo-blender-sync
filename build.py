import os
import zipfile
import shutil

def build_release():
    print("Building distribution package...")
    
    # Create dist folder
    if not os.path.exists("dist"):
        os.makedirs("dist")
        
    zip_path = "dist/ingetrazo_blender_sync_v1.0.zip"
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add Blender addon
        zf.write("blender_addon/ingetrazo_sync.py", "Blender_Addon/ingetrazo_sync.py")
        
        # Add IngeTrazo plugin
        zf.write("ingetrazo_plugin/blender_sync.py", "IngeTrazo_Plugin/blender_sync.py")
        
        # Add Documentation and License
        zf.write("README.md", "README.md")
        zf.write("LICENSE", "LICENSE")
        
        # Add docs folder
        for root, dirs, files in os.walk("docs"):
            for file in files:
                file_path = os.path.join(root, file)
                zf.write(file_path, file_path)

    print(f"Successfully created: {zip_path}")
    print("This zip file is ready to be uploaded to a GitHub Release!")

if __name__ == "__main__":
    build_release()
