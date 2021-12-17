rustup target add aarch64-unknown-linux-gnu
rustup target add aarch64-unknown-linux-musl
sudo apt-get install -y gcc-aarch64-linux-gnu
cargo build --target=aarch64-unknown-linux-musl