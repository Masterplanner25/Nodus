fn read(path) {
    return read_file(path)
}

fn write(path, content) {
    return write_file(path, content)
}

fn append(path, content) {
    return append_file(path, content)
}

fn ensure_dir(path) {
    mkdir(path)
    return path
}

fn exists_path(path) {
    return exists(path)
}
