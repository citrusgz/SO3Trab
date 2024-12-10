import os
import struct

class FURGfs:
    def __init__(self, size_mb, filename='furgfs2.fs'):
        self.size_mb = size_mb
        self.block_size = 4096
        self.max_filename_length = 10 + 4
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

                fs_file.seek(self.fat_start)
                for block_index in range(self.size_mb * 1024 * 1024 // self.block_size):
                    fat_entry = fs_file.read(4)
                    if fat_entry == b'\x00\x00\x00\x00':
                        fs_file.seek(-4, os.SEEK_CUR)
                        fs_file.write(struct.pack('I', block_index + 1))
                        fs_file.seek(self.data_start + block_index * self.block_size)
                        fs_file.write(data[:self.block_size])
                        data = data[self.block_size:]
                        if not data:
                            break
                else:
                    raise Exception("Not enough space in the file system")

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

    def show_file_content(self, filename):
        with open(self.filename, 'rb') as fs_file:
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                if not entry:
                    break
                entry_filename = entry[:self.max_filename_length].rstrip(b'\x00').decode('utf-8')
                if entry_filename == filename:
                    fs_file.seek(self.data_start)
                    content = fs_file.read().decode('utf-8')
                    print(f"Content of '{filename}':")
                    print(content)
                    return
        raise FileNotFoundError(f"File '{filename}' not found in the file system")

    @staticmethod
    def menu():
        filename = input("Enter the file system filename (default 'furgfs2.fs'): ") or 'furgfs2.fs'
        if os.path.exists(filename):
            choice = input(f"File '{filename}' exists. Do you want to use it? (y/n): ").lower()
            if choice == 'y':
                size_mb = None
            else:
                size_mb = input("Enter the file system size in MB (default 800MB): ") or 800
                size_mb = int(size_mb)
        else:
            size_mb = input("Enter the file system size in MB (default 800MB): ") or 800
            size_mb = int(size_mb)
        fs = FURGfs(size_mb if size_mb is not None else 800, filename)
        while True:
            print(f"\n{fs.filename} File System Menu")
            print("1. Show file content")
            print("2. Copy file out of FS")
            print("3. Rename file")
            print("4. Remove file")
            print("5. List files")
            print("6. Check free space")
            print("7. Protect file")
            print("8. Unprotect file (not working as expected)")
            print("9. Create text file")
            print("10. Copy file to FS")
            print("24. Exit")
            choice = input("Enter your choice: ")

            if choice == '1':
                filename = input("Enter the file name: ")
                try:
                    fs.show_file_content(filename)
                except FileNotFoundError as e:
                    print(e)
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
                MBfree_space = free_space / (1024 * 1024)
                print(f"Free space in FS: {MBfree_space} MB de {fs.size_mb} MB.")
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
                src_name = input("Enter the source file name: ")
                dest_dir = input("Enter the destination directory name: ")
                try:
                    fs.move(src_name, dest_dir)
                    print(f"File '{src_name}' moved to directory '{dest_dir}'.")
                except FileNotFoundError as e:
                    print(e)
            elif choice == '10':
                src_path = input("Enter the source file path: ")
                fs.copy_to_fs(src_path)
                print(f"File '{src_path}' copied to FS.")
            elif choice == '24':
                print("Exiting...")
                break
            else:
                print("Invalid choice. Please try again.")

if __name__ == '__main__':
    FURGfs.menu()
