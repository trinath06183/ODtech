import os
import glob
import subprocess
import threading
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse, Http404
from core.decorators import role_required
from django.core.files.storage import FileSystemStorage

BACKUP_DIR = "/home/server_admin/backups"

@role_required('Admin')
def backup_manager_view(request):
    """View to list all backups."""
    backups = []
    if os.path.exists(BACKUP_DIR):
        files = glob.glob(os.path.join(BACKUP_DIR, "odtech_backup_*.tar.gz"))
        for f in sorted(files, reverse=True):
            stat = os.stat(f)
            backups.append({
                'name': os.path.basename(f),
                'size': stat.st_size,
                'created': stat.st_mtime
            })
    
    return render(request, 'config/backup_manager.html', {
        'backups': backups,
        'title': 'Backup & Restore'
    })

@role_required('Admin')
def backup_create_view(request):
    """Trigger the auto-backup script and redirect back."""
    if request.method == 'POST':
        if os.name == 'nt':
            messages.warning(request, "Backup creation is only supported on the production Linux server.")
        else:
            try:
                # We call the script installed on the server
                result = subprocess.run(["/usr/local/bin/odtech-autobackup"], capture_output=True, text=True)
                if result.returncode == 0:
                    messages.success(request, "Backup created successfully!")
                else:
                    messages.error(request, f"Backup failed: {result.stderr}")
            except Exception as e:
                messages.error(request, f"Failed to execute backup script: {e}")
            
    return redirect('backup_manager')

@role_required('Admin')
def backup_download_view(request, filename):
    """Download a specific backup file."""
    if not filename.startswith("odtech_backup_") or not filename.endswith(".tar.gz"):
        raise Http404("Invalid backup filename.")
        
    filepath = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(filepath):
        raise Http404("Backup file not found.")
        
    with open(filepath, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/gzip')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

def restore_worker(filepath):
    """Background worker that performs the restoration."""
    try:
        extract_dir = "/tmp/restore_odtech"
        os.makedirs(extract_dir, exist_ok=True)
        subprocess.run(["tar", "-xzf", filepath, "-C", extract_dir], check=True)
        
        sql_files = glob.glob(os.path.join(extract_dir, "tmp", "odtech_db_*.sql"))
        if sql_files:
            sql_file = sql_files[0]
            restore_script = f"""#!/bin/bash
export $(grep -v '^#' /home/server_admin/ODtech/.env | xargs)
PGPASSWORD=$POSTGRES_PASSWORD psql -U $POSTGRES_USER -h ${{POSTGRES_HOST:-localhost}} -p ${{POSTGRES_PORT:-5432}} $POSTGRES_DB < "{sql_file}"

if [ -d "{extract_dir}/home/server_admin/ODtech/media" ]; then
    cp -r {extract_dir}/home/server_admin/ODtech/media/* /home/server_admin/ODtech/media/
fi

rm -rf "{extract_dir}"
rm "{filepath}"
"""
            script_path = "/tmp/run_restore.sh"
            with open(script_path, "w") as f:
                f.write(restore_script)
            
            subprocess.run(["bash", script_path], check=True)
            
    except Exception as e:
        print(f"Restore failed: {e}")

@role_required('Admin')
def backup_restore_view(request):
    """Handle uploading a backup file and restoring it."""
    if request.method == 'POST' and request.FILES.get('backup_file'):
        uploaded_file = request.FILES['backup_file']
        if not uploaded_file.name.endswith('.tar.gz'):
            messages.error(request, "Only .tar.gz backup files are allowed.")
            return redirect('backup_manager')
            
        fs = FileSystemStorage(location='/tmp')
        filename = fs.save(uploaded_file.name, uploaded_file)
        filepath = fs.path(filename)
        
        thread = threading.Thread(target=restore_worker, args=(filepath,))
        thread.start()
        
        return render(request, 'config/backup_restoring.html')
        
    return redirect('backup_manager')
