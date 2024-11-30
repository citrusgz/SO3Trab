import os
import struct
import zipfile
import tarfile
import curses
import time

class FURGfs2:
    def __init__(self, size_mb, filename='furgfs2.fs'):
        self.size_mb = size_mb
        self.block_size = 4096
        self.max_filename_length = 255
        self.header_size = 1024
        self.fat_start = self.header_size
        self.root_dir_start = self.fat_start + (self.size_mb * 1024 * 1024 // self.block_size) * 4
        self.data_start = self.root_dir_start + (self.max_filename_length + 8) * 1024
        self.filename = filename
        if not os.path.exists(self.filename):
            self.create_fs()

    def create_fs(self):
        with open(self.filename, 'wb') as f:
            f.write(b'\x00' * (self.size_mb * 1024 * 1024))
            f.seek(0)
            f.write(struct.pack('I', self.header_size))
            f.write(struct.pack('I', self.block_size))
            f.write(struct.pack('I', self.size_mb * 1024 * 1024))
            f.write(struct.pack('I', self.fat_start))
            f.write(struct.pack('I', self.root_dir_start))
            f.write(struct.pack('I', self.data_start))

    def copy_to_fs(self, src_path):
        if os.path.isdir(src_path):
            raise IsADirectoryError(f"Provided path '{src_path}' is a directory, not a file.")
        with open(src_path, 'rb') as src_file:
            data = src_file.read()
            with open(self.filename, 'r+b') as fs_file:
                fs_file.seek(self.root_dir_start)
                for _ in range(1024):
                    entry = fs_file.read(self.max_filename_length + 8)
                    if entry[:self.max_filename_length].rstrip(b'\x00') == b'':
                        fs_file.seek(-len(entry), os.SEEK_CUR)
                        filename_bytes = os.path.basename(src_path).encode('utf-8').ljust(self.max_filename_length, b'\x00')
                        fs_file.write(filename_bytes + b'\x00' * 8)
                        break
                else:
                    raise Exception("Root directory is full")

                fs_file.seek(self.data_start)
                fs_file.write(data)

    def copy_from_fs(self, dest_path):
        with open(self.filename, 'rb') as fs_file:
            fs_file.seek(self.data_start)
            data = fs_file.read()
            with open(dest_path, 'wb') as dest_file:
                dest_file.write(data)

    def rename_file(self, old_name, new_name):
        with open(self.filename, 'r+b') as fs_file:
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                if not entry:
                    break
                filename = entry[:self.max_filename_length].rstrip(b'\x00').decode('utf-8')
                if filename == old_name:
                    new_name_bytes = new_name.encode('utf-8').ljust(self.max_filename_length, b'\x00')
                    fs_file.seek(-len(entry), os.SEEK_CUR)
                    fs_file.write(new_name_bytes + entry[self.max_filename_length:])
                    return
        raise FileNotFoundError(f"File '{old_name}' not found in the file system")

    def remove_file(self, filename):
        with open(self.filename, 'r+b') as fs_file:
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                if not entry:
                    break
                entry_filename = entry[:self.max_filename_length].rstrip(b'\x00').decode('utf-8')
                if entry_filename == filename:
                    fs_file.seek(-len(entry), os.SEEK_CUR)
                    fs_file.write(b'\x00' * len(entry))
                    return
        raise FileNotFoundError(f"File '{filename}' not found in the file system")

    def list_files(self):
        files = []
        with open(self.filename, 'rb') as fs_file:
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                if not entry:
                    return files
                filename = entry[:self.max_filename_length].rstrip(b'\x00').decode('utf-8')
                if filename:
                    files.append(filename)
        return files

    def free_space(self):
        total_blocks = self.size_mb * 1024 * 1024 // self.block_size
        used_blocks = 0
        with open(self.filename, 'rb') as fs_file:
            fs_file.seek(self.fat_start)
            for _ in range(total_blocks):
                entry = fs_file.read(4)
                if entry != b'\x00\x00\x00\x00':
                    used_blocks += 1
        free_blocks = total_blocks - used_blocks
        return free_blocks * self.block_size

    def protect_file(self, filename):
        with open(self.filename, 'r+b') as fs_file:
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                if not entry:
                    break
                entry_filename = entry[:self.max_filename_length].rstrip(b'\x00').decode('utf-8')
                if entry_filename == filename:
                    fs_file.seek(-len(entry), os.SEEK_CUR)
                    protected_flag = b'\x01'
                    fs_file.write(entry[:self.max_filename_length] + protected_flag + entry[self.max_filename_length + 1:])
                    return
        raise FileNotFoundError(f"File '{filename}' not found in the file system")

    def unprotect_file(self, filename):
        with open(self.filename, 'r+b') as fs_file:
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                if not entry:
                    break
                entry_filename = entry[:self.max_filename_length].rstrip(b'\x00').decode('utf-8')
                if entry_filename == filename:
                    fs_file.seek(-len(entry), os.SEEK_CUR)
                    unprotected_flag = b'\x00'
                    fs_file.write(entry[:self.max_filename_length] + unprotected_flag + entry[self.max_filename_length + 1:])
                    return
        raise FileNotFoundError(f"File '{filename}' not found in the file system")
    
    def create_text_file(self, filename, content):
        with open(self.filename, 'r+b') as fs_file:
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                if entry[:self.max_filename_length].rstrip(b'\x00') == b'':
                    fs_file.seek(-len(entry), os.SEEK_CUR)
                    filename_bytes = filename.encode('utf-8').ljust(self.max_filename_length, b'\x00')
                    fs_file.write(filename_bytes + b'\x00' * 8)
                    break
            else:
                raise Exception("Root directory is full")

            fs_file.seek(self.data_start)
            fs_file.write(content.encode('utf-8'))

    def create_directory(self, dirname):
        with open(self.filename, 'r+b') as fs_file:
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                if entry[:self.max_filename_length].rstrip(b'\x00') == b'':
                    fs_file.seek(-len(entry), os.SEEK_CUR)
                    dirname_bytes = dirname.encode('utf-8').ljust(self.max_filename_length, b'\x00')
                    fs_file.write(dirname_bytes + b'\x01' + b'\x00' * 7)
                    return
            else:
                raise Exception("Root directory is full")
            
    def move(self, src_name, dest_dir):
        with open(self.filename, 'r+b') as fs_file:
            fs_file.seek(self.root_dir_start)
            src_entry = None
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                if not entry:
                    break
                filename = entry[:self.max_filename_length].rstrip(b'\x00').decode('utf-8')
                if filename == src_name:
                    src_entry = entry
                    fs_file.seek(-len(entry), os.SEEK_CUR)
                    fs_file.write(b'\x00' * len(entry))
                    break
            if not src_entry:
                raise FileNotFoundError(f"Source '{src_name}' not found in the file system")

            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                dirname = entry[:self.max_filename_length].rstrip(b'\x00').decode('utf-8')
                if dirname == dest_dir:
                    fs_file.seek(-len(entry), os.SEEK_CUR)
                    fs_file.write(src_entry[:self.max_filename_length] + b'\x01' + src_entry[self.max_filename_length + 1:])
                    return
            raise FileNotFoundError(f"Destination directory '{dest_dir}' not found in the file system")
        
    def compress_file(self, filename, compression_type):
        if compression_type == 'zip':
            with zipfile.ZipFile(f'{filename}.zip', 'w') as zipf:
                zipf.write(filename, os.path.basename(filename))
        elif compression_type == 'tar':
            with tarfile.open(f'{filename}.tar', 'w') as tarf:
                tarf.add(filename, arcname=os.path.basename(filename))
        elif compression_type == 'tar.gz':
            with tarfile.open(f'{filename}.tar.gz', 'w:gz') as tarf:
                tarf.add(filename, arcname=os.path.basename(filename))
        else:
            raise ValueError("Unsupported compression type. Choose 'zip', 'tar', or 'tar.gz'.")
        
    def current_directory(self):
        with open(self.filename, 'rb') as fs_file:
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                if not entry:
                    break
                dirname = entry[:self.max_filename_length].rstrip(b'\x00').decode('utf-8')
                if dirname:
                    return dirname
        return "/"
    
    def change_directory(self, dirname):
        with open(self.filename, 'r+b') as fs_file:
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                if not entry:
                    break
                entry_name = entry[:self.max_filename_length].rstrip(b'\x00').decode('utf-8')
                if entry_name == dirname and entry[self.max_filename_length] == b'\x01'[0]:
                    self.root_dir_start = fs_file.tell() - len(entry)
                    return
        raise FileNotFoundError(f"Directory '{dirname}' not found in the file system")

    @staticmethod
    def menu():
        filename = input("Enter the file system filename (default 'furgfs2.fs'): ") or 'furgfs2.fs'
        size_mb = int(input("Enter the file system size in MB (default 800MB): ") or 800)
        fs = FURGfs2(size_mb, filename)
        while True:
            print(f"{fs.filename} File System Menu")
            print("1. Copy file to FS")
            print("2. Copy file from FS")
            print("3. Rename file")
            print("4. Remove file from FS")
            print("5. List files")
            print("6. Check free space")
            print("7. Protect file")
            print("8. Unprotect file")
            print("9. Create text file")
            print("10. Create directory")
            print("11. Move file")
            print("12. Compress file")
            print("13. Show current directory")
            print("14. Change directory")
            print("15. Exit")
            choice = input("Enter your choice: ")

            if choice == '1':
                src_path = input("Enter the source file path: ")
                fs.copy_to_fs(src_path)
                print(f"File '{src_path}' copied to FS.")
            elif choice == '2':
                dest_path = input("Enter the destination file path: ")
                fs.copy_from_fs(dest_path)
                print(f"File copied from FS to '{dest_path}'.")
            elif choice == '3':
                old_name = input("Enter the old file name: ")
                new_name = input("Enter the new file name: ")
                try:
                    fs.rename_file(old_name, new_name)
                    print(f"File '{old_name}' renamed to '{new_name}'.")
                except FileNotFoundError as e:
                    print(e)
            elif choice == '4':
                filename = input("Enter the file name to remove: ")
                try:
                    fs.remove_file(filename)
                    print(f"File '{filename}' removed from FS.")
                except FileNotFoundError as e:
                    print(e)
            elif choice == '5':
                files = fs.list_files()
                print("Files in FS:")
                for file in files:
                    print(file)
            elif choice == '6':
                free_space = fs.free_space()
                print(f"Free space in FS: {free_space} bytes")
            elif choice == '7':
                filename = input("Enter the file name to protect: ")
                try:
                    fs.protect_file(filename)
                    print(f"File '{filename}' protected in FS.")
                except FileNotFoundError as e:
                    print(e)
            elif choice == '8':
                filename = input("Enter the file name to unprotect: ")
                try:
                    fs.unprotect_file(filename)
                    print(f"File '{filename}' unprotected in FS.")
                except FileNotFoundError as e:
                    print(e)
            elif choice == '9':
                filename = input("Enter the file name: ")
                content = input("Enter the file content: ")
                fs.create_text_file(filename, content)
                print(f"Text file '{filename}' created in FS.")
            elif choice == '10':
                dirname = input("Enter the directory name: ")
                fs.create_directory(dirname)
                print(f"Directory '{dirname}' created in FS.")
            elif choice == '11':
                src_name = input("Enter the source file name: ")
                dest_dir = input("Enter the destination directory name: ")
                try:
                    fs.move(src_name, dest_dir)
                    print(f"File '{src_name}' moved to directory '{dest_dir}'.")
                except FileNotFoundError as e:
                    print(e)
            elif choice == '12':
                filename = input("Enter the file name to compress: ")
                compression_type = input("Enter the compression type (zip, tar, tar.gz): ")
                try:
                    fs.compress_file(filename, compression_type)
                    print(f"File '{filename}' compressed in FS.")
                except ValueError as e:
                    print(e)
            elif choice == '13':
                print(f"Current directory: {fs.current_directory()}")
            elif choice == '14':
                dirname = input("Enter the directory name: ")
                try:
                    fs.change_directory(dirname)
                    print(f"Changed to directory '{dirname}'.")
                except FileNotFoundError as e:
                    print(e)
            elif choice == '15':
                print("Exiting...")
                break
            else:
                print("Invalid choice. Please try again.")


def init_animation(stdscr):
    curses.curs_set(0)  # Ocultar o cursor
    stdscr.nodelay(1)  # Permitir leitura não bloqueante
    stdscr.timeout(100)  # Atualiza a tela a cada 100ms

    # Frames do pinguim (balançando)
    presentation = [
        r"""
      _____                    _____                    _____                    _____                    _____                    _____          
     /\    \                  /\    \                  /\    \                  /\    \                  /\    \                  /\    \         
    /::\    \                /::\    \                /::\____\                /::\    \                /::\    \                /::\    \        
    \:::\    \              /::::\    \              /:::/    /               /::::\    \               \:::\    \              /::::\    \       
     \:::\    \            /::::::\    \            /:::/    /               /::::::\    \               \:::\    \            /::::::\    \      
      \:::\    \          /:::/\:::\    \          /:::/    /               /:::/\:::\    \               \:::\    \          /:::/\:::\    \     
       \:::\    \        /:::/__\:::\    \        /:::/____/               /:::/__\:::\    \               \:::\    \        /:::/__\:::\    \    
       /::::\    \      /::::\   \:::\    \      /::::\    \              /::::\   \:::\    \              /::::\    \      /::::\   \:::\    \   
      /::::::\    \    /::::::\   \:::\    \    /::::::\____\________    /::::::\   \:::\    \    ____    /::::::\    \    /::::::\   \:::\    \  
     /:::/\:::\    \  /:::/\:::\   \:::\    \  /:::/\:::::::::::\    \  /:::/\:::\   \:::\ ___\  /\   \  /:::/\:::\    \  /:::/\:::\   \:::\____\ 
    /:::/  \:::\____\/:::/  \:::\   \:::\____\/:::/  |:::::::::::\____\/:::/__\:::\   \:::|    |/::\   \/:::/  \:::\____\/:::/  \:::\   \:::|    |
   /:::/    \::/    /\::/    \:::\  /:::/    /\::/   |::|~~~|~~~~~     \:::\   \:::\  /:::|____|\:::\  /:::/    \::/    /\::/   |::::\  /:::|____|
  /:::/    / \/____/  \/____/ \:::\/:::/    /  \/____|::|   |           \:::\   \:::\/:::/    /  \:::\/:::/    / \/____/  \/____|:::::\/:::/    / 
 /:::/    /                    \::::::/    /         |::|   |            \:::\   \::::::/    /    \::::::/    /                 |:::::::::/    /  
/:::/    /                      \::::/    /          |::|   |             \:::\   \::::/    /      \::::/____/                  |::|\::::/    /   
\::/    /                       /:::/    /           |::|   |              \:::\  /:::/    /        \:::\    \                  |::| \::/____/    
 \/____/                       /:::/    /            |::|   |               \:::\/:::/    /          \:::\    \                 |::|  ~|          
                              /:::/    /             |::|   |                \::::::/    /            \:::\    \                |::|   |          
                             /:::/    /              \::|   |                 \::::/    /              \:::\____\               \::|   |          
                             \::/    /                \:|   |                  \::/____/                \::/    /                \:|   |          
                              \/____/                  \|___|                   ~~                       \/____/                  \|___|          
                                                                                                                                                  
                                                     
        """
        
    ]

    start_time = time.time()
    frame_idx = 0

    while True:
        elapsed_time = time.time() - start_time
        if elapsed_time > 3:
            break

        # Limpar a tela
        stdscr.clear()

        # Atualizar frame
        frame = presentation[frame_idx]
        stdscr.addstr(5, 10, frame)
        frame_idx = (frame_idx + 1) % len(presentation)

        # Atualizar tela
        stdscr.refresh()

        # Aguarda próximo frame
        time.sleep(0.5)


if __name__ == '__main__':
    curses.wrapper(init_animation)
    FURGfs2.menu()
