import os
import struct

class FURGfs:
    def __init__(self, size_mb, filename='furgfs2.fs'):
        self.size_mb = size_mb
        self.block_size = 4096
        self.max_filename_length = 255 # Max length of filename with extension
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

            fs_file.seek(self.fat_start)
            for block_index in range(self.size_mb * 1024 * 1024 // self.block_size):
                fat_entry = fs_file.read(4)
                if fat_entry == b'\x00\x00\x00\x00':
                    fs_file.seek(-4, os.SEEK_CUR)
                    fs_file.write(struct.pack('I', block_index + 1))
                    fs_file.seek(self.data_start + block_index * self.block_size)
                    fs_file.write(content.encode('utf-8')[:self.block_size])
                    content = content[self.block_size:]
                    if not content:
                        break
            else:
                raise Exception("Not enough space in the file system")

    def show_file_content(self, filename):
        with open(self.filename, 'rb') as fs_file:
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                entry_filename = entry[:self.max_filename_length].rstrip(b'\x00').decode('utf-8')
                if entry_filename == filename:
                    if entry[self.max_filename_length] == 1:
                        print(f"File '{filename}' is protected and cannot be read.")
                        return
                    fs_file.seek(self.data_start)
                    data = fs_file.read()
                    print(data.decode('utf-8'))
                    return
        raise FileNotFoundError(f"File '{filename}' not found in the file system")

    def copy_to_fs(self, src_path):
        with open(src_path, 'rb') as src_file:
            content = src_file.read()
            filename = os.path.basename(src_path)
            self.create_binary_file(filename, content)

    def create_binary_file(self, filename, content):
        with open(self.filename, 'r+b') as fs_file:
            # Step 1: Find empty root directory entry
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                if entry[:self.max_filename_length].rstrip(b'\x00') == b'':
                    # Empty entry found
                    fs_file.seek(-len(entry), os.SEEK_CUR)
                    filename_bytes = filename.encode('utf-8').ljust(self.max_filename_length, b'\x00')
                    # Placeholder for starting block index and file size
                    fs_file.write(filename_bytes + b'\x00' * 8)
                    root_dir_entry_pos = fs_file.tell() - (self.max_filename_length + 8)
                    break
            else:
                raise Exception("Root directory is full")

            # Step 2: Allocate blocks and build FAT chain
            total_blocks = (len(content) + self.block_size - 1) // self.block_size
            free_blocks = []
            fs_file.seek(self.fat_start)
            for block_index in range(self.size_mb * 1024 * 1024 // self.block_size):
                fs_file.seek(self.fat_start + block_index * 4)
                fat_entry = fs_file.read(4)
                if struct.unpack('I', fat_entry)[0] == 0:
                    free_blocks.append(block_index)
                    if len(free_blocks) == total_blocks:
                        break
            else:
                raise Exception("Not enough space in the file system")

            # Step 3: Write data blocks and update FAT
            for i, block_index in enumerate(free_blocks):
                # Write data block
                fs_file.seek(self.data_start + block_index * self.block_size)
                fs_file.write(content[i * self.block_size:(i + 1) * self.block_size])

                # Update FAT entry
                fs_file.seek(self.fat_start + block_index * 4)
                if i < len(free_blocks) - 1:
                    # Point to next block
                    fs_file.write(struct.pack('I', free_blocks[i + 1]))
                else:
                    # Last block, mark end of file (EOF)
                    fs_file.write(struct.pack('I', 0xFFFFFFFF))

            # Step 4: Update root directory entry with starting block and file size
            fs_file.seek(root_dir_entry_pos)
            filename_bytes = filename.encode('utf-8').ljust(self.max_filename_length, b'\x00')
            starting_block = struct.pack('I', free_blocks[0])
            file_size = struct.pack('I', len(content))
            fs_file.write(filename_bytes + starting_block + file_size)

    def copy_from_fs(self, filename, dest_path):
        with open(self.filename, 'rb') as fs_file:
            # Step 1: Find the root directory entry
            fs_file.seek(self.root_dir_start)
            for _ in range(1024):
                entry = fs_file.read(self.max_filename_length + 8)
                entry_filename = entry[:self.max_filename_length].rstrip(b'\x00').decode('utf-8')
                if entry_filename == filename:
                    starting_block = struct.unpack('I', entry[self.max_filename_length:self.max_filename_length + 4])[0]
                    file_size = struct.unpack('I', entry[self.max_filename_length + 4:self.max_filename_length + 8])[0]

                    # Step 2: Read data blocks following FAT chain
                    data = b''
                    current_block = starting_block
                    bytes_remaining = file_size
                    while True:
                        fs_file.seek(self.data_start + current_block * self.block_size)
                        data_block = fs_file.read(min(self.block_size, bytes_remaining))
                        data += data_block
                        bytes_remaining -= len(data_block)
                        if bytes_remaining <= 0:
                            break
                        fs_file.seek(self.fat_start + current_block * 4)
                        fat_entry = struct.unpack('I', fs_file.read(4))[0]
                        if fat_entry == 0xFFFFFFFF:
                            break
                        current_block = fat_entry

                    # Step 3: Write data to destination file
                    with open(os.path.join(dest_path, filename), 'wb') as dest_file:
                        dest_file.write(data)
                    return
            raise FileNotFoundError(f"File '{filename}' not found in the file system")

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
            print("1. Show file content (need to be fixed)")
            print("2. Copy file out of FS")
            print("3. Rename file")
            print("4. Remove file")
            print("5. List files (need to be fixed)")
            print("6. Check free space")
            print("7. Protect file")
            print("8. Unprotect file")
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
                filename = input("Enter the file name: ")
                dest_path = input("Enter the destination file path: ")
                try:
                    fs.copy_from_fs(filename, dest_path)
                    print(f"File '{filename}' copied from FS to '{dest_path}'.")
                except FileNotFoundError as e:
                    print(e)
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
            elif choice == '10':
                src_path = input("Enter the source file path: ")
                fs.copy_to_fs(src_path)
                print(f"File '{src_path}' copied to FS.")
            elif choice == '11':
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
