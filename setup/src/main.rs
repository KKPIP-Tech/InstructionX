use clap::Parser;
use instructionx_setup::cli::{Cli, execute, normalize_legacy_args};

fn main() {
    let cli = Cli::parse_from(normalize_legacy_args(std::env::args()));
    if let Err(error) = execute(cli) {
        eprintln!("InstructionX Setup: {error}");
        std::process::exit(1);
    }
}
