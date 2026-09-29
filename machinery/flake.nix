{
  description = "Boundary measurement build tools; language releases are checksum-pinned separately";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }: let
    pkgs = import nixpkgs { system = "aarch64-linux"; };
  in {
    devShells.aarch64-linux.default = pkgs.mkShell {
      packages = with pkgs; [ uv gcc pkg-config openssl protobuf cmake perl rustup git ];
      SSL_CERT_FILE = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";
    };
  };
}
