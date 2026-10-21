"""CLI entry point for NOS compiler.

Provides command-line interface for compiling NOS files.
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .. import __version__
from .pipeline import CompilerPipeline, CompilationResult

SOURCE_SUFFIXES = ('.node', '.interface')
LEGACY_SUFFIX = '.nos'

logger = logging.getLogger("nos")


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog='nos',
        description='NOS compiler for ROS2'
    )

    parser.add_argument(
        'files',
        nargs='*',
        help='NOS source files (.node, .interface). Files that declare the same '
             'package are compiled into one ROS 2 package.'
    )

    parser.add_argument(
        '-o', '--output',
        default='./generated',
        help='Output directory for generated files (default: ./generated)'
    )

    parser.add_argument(
        '-t', '--target',
        choices=['python'],
        default='python',
        help='Target language (default: python)'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Parse and analyze but do not generate output'
    )

    parser.add_argument(
        '--no-build',
        action='store_true',
        help='Skip automatic colcon build after generation'
    )

    parser.add_argument(
        '--no-build-cache',
        action='store_true',
        help='Disable build cache (forces colcon build every time)'
    )

    parser.add_argument(
        '--run',
        action='store_true',
        help='After compiling a single input file that generates exactly one node, '
             'run that node with the current Python interpreter '
             '(ROS 2 must already be sourced). Not valid with --dry-run.'
    )

    parser.add_argument(
        '--install-vscode',
        action='store_true',
        help='Install or update the VS Code syntax highlighting extension, then exit'
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )

    return parser


def format_result(result: CompilationResult, file_path: str) -> str:
    """Format compilation result for display."""
    lines = []

    if result.success:
        lines.append(f"✓ {file_path}")
        if result.files:
            lines.append(f"  Generated {len(result.files)} file(s):")
            for f in result.files:
                lines.append(f"    - {f}")
    else:
        lines.append(f"✗ {file_path}")

    if result.warnings:
        lines.append(f"  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            lines.append(f"    ! {w}")

    if result.errors:
        lines.append(f"  Errors ({len(result.errors)}):")
        for e in result.errors:
            lines.append(f"    ✗ {e}")

    return "\n".join(lines)


def install_vscode_extension(home: Optional[Path] = None) -> bool:
    """Install or update the bundled VS Code extension in ``~/.vscode/extensions``.

    An existing copy is replaced when its version differs from the bundled one.
    Failures are reported on stderr; returns True on success.
    """
    import json

    home = home or Path.home()
    src = Path(__file__).parent.parent / "extensions" / "vscode-nos"
    dest = home / ".vscode" / "extensions" / "vscode-nos"

    if not src.is_dir():
        print(f"error: bundled VS Code extension not found at {src}", file=sys.stderr)
        return False

    try:
        def version_of(directory: Path) -> Optional[str]:
            try:
                return json.loads((directory / "package.json").read_text(encoding="utf-8")).get("version")
            except (OSError, ValueError):
                return None

        if dest.exists():
            if version_of(dest) == version_of(src):
                print(f"VS Code extension is already up to date: {dest}")
                return True
            shutil.rmtree(dest)
            action = "updated"
        else:
            action = "installed"

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        print(f"VS Code extension {action}: {dest}")
        return True
    except OSError as e:
        print(f"error: could not install the VS Code extension into {dest}: {e}", file=sys.stderr)
        return False


def _validate_inputs(files: List[str]) -> List[str]:
    """Return one message per unusable input file."""
    problems = []
    for f in files:
        path = Path(f)
        suffix = path.suffix.lower()
        if not path.exists():
            problems.append(f"File not found: {f}")
        elif suffix == LEGACY_SUFFIX:
            problems.append(
                f"{f}: the '{LEGACY_SUFFIX}' extension is no longer supported; "
                f"rename the file to '{path.with_suffix('.node').name}'"
            )
        elif suffix not in SOURCE_SUFFIXES:
            problems.append(f"Invalid file type: {f} (expected .node or .interface)")
    return problems


def _node_modules(result: CompilationResult) -> List[str]:
    """Generated node module file names (the things ``--run`` can start)."""
    return sorted(name for name in result.files if name.endswith('_node.py'))


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI.

    Args:
        args: Command line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = create_parser()
    parsed = parser.parse_args(args)

    logging.basicConfig(
        level=logging.INFO if parsed.verbose else logging.WARNING,
        format="%(message)s",
        stream=sys.stderr,
    )

    if parsed.install_vscode:
        return 0 if install_vscode_extension() else 1

    if not parsed.files:
        parser.error("the following arguments are required: files")

    problems = _validate_inputs(parsed.files)
    if problems:
        for problem in problems:
            print(f"Error: {problem}", file=sys.stderr)
        return 1

    if parsed.run and parsed.dry_run:
        print("Error: --run cannot be combined with --dry-run", file=sys.stderr)
        return 1
    if parsed.run and len(parsed.files) != 1:
        print("Error: --run needs exactly one input file", file=sys.stderr)
        return 1

    pipeline = CompilerPipeline({
        'target': parsed.target,
        'verbose': parsed.verbose,
        'auto_build': not parsed.no_build,
        'build_cache': not parsed.no_build_cache,
    })

    failure_count = 0
    succeeded: Dict[str, CompilationResult] = {}

    for file_path in parsed.files:
        result = pipeline.compile_file(file_path)
        if result.success:
            succeeded[file_path] = result
            if parsed.verbose or result.warnings:
                print(format_result(result, file_path), file=sys.stderr if result.warnings else sys.stdout)
        else:
            failure_count += 1
            print(format_result(result, file_path), file=sys.stderr)
            print(file=sys.stderr)

    # Inputs that share a package are written together: one scaffold, all entry points.
    by_package: Dict[str, List[str]] = {}
    for file_path, result in succeeded.items():
        by_package.setdefault(result.package_name, []).append(file_path)

    written: Optional[Path] = None
    for package_name, paths in by_package.items():
        merged = CompilationResult.merge([succeeded[p] for p in paths])
        label = ", ".join(paths)
        if not merged.success:
            failure_count += len(paths)
            print(format_result(merged, label), file=sys.stderr)
            continue
        if parsed.dry_run:
            continue
        if pipeline.write_outputs(merged, parsed.output):
            package_dir = Path(parsed.output) / "ros2_ws" / "src" / package_name / package_name
            nodes_ = _node_modules(merged)
            if len(nodes_) == 1:
                written = package_dir / nodes_[0]
            elif parsed.run:
                print(f"Error: --run needs a single node, but {label} generates "
                      f"{len(nodes_)}: {', '.join(nodes_) or 'none'}", file=sys.stderr)
                return 1
        else:
            failure_count += len(paths)
            print(format_result(merged, label), file=sys.stderr)

    if parsed.run and failure_count == 0 and written is not None:
        logger.info("Running: %s", written)

        # Make a source checkout of nos importable if it is not installed
        env = os.environ.copy()
        project_root = str(Path(__file__).parent.parent.parent)
        env['PYTHONPATH'] = project_root + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')

        try:
            subprocess.run([sys.executable, str(written)], env=env, check=True)
        except KeyboardInterrupt:
            pass
        except subprocess.CalledProcessError as e:
            print(f"Error running node: {e}", file=sys.stderr)
            return 1

    if parsed.verbose:
        ok = len(parsed.files) - failure_count
        print(f"\nSummary: {ok} succeeded, {failure_count} failed")

    return 0 if failure_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
