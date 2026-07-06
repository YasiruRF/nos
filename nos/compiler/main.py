"""CLI entry point for NOS compiler.

Provides command-line interface for compiling NOS files.
"""

import argparse
import sys
import subprocess
import os
from pathlib import Path

from .pipeline import CompilerPipeline, CompilationResult


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog='nos',
        description='NOS compiler for ROS2'
    )

    parser.add_argument(
        'files',
        nargs='+',
        help='NOS source files (.nos, .node, .interface)'
    )

    parser.add_argument(
        '-o', '--output',
        default='./generated',
        help='Output directory for generated files (default: ./generated)'
    )

    parser.add_argument(
        '-t', '--target',
        choices=['python', 'cpp'],
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
        help='Automatically run the generated node after compilation'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 0.1.0'
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


def main(args: list = None) -> int:
    """Main entry point for the CLI.

    Args:
        args: Command line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = create_parser()
    parsed = parser.parse_args(args)

    # Validate input files
    invalid_files = []
    for f in parsed.files:
        path = Path(f)
        if not path.exists():
            invalid_files.append(f"File not found: {f}")
        elif not path.suffix in ['.nos', '.node', '.interface']:
            invalid_files.append(f"Invalid file type: {f}")

    if invalid_files:
        for error in invalid_files:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    # Configure pipeline
    options = {
        'target': parsed.target,
        'verbose': parsed.verbose,
        'auto_build': not parsed.no_build,
        'build_cache': not parsed.no_build_cache
    }

    pipeline = CompilerPipeline(options)

    # Compile files
    success_count = 0
    failure_count = 0
    last_generated_file = None

    for file_path in parsed.files:
        result = pipeline.compile_file(file_path)

        if parsed.verbose or not result.success:
            print(format_result(result, file_path))
            print()

        if result.success:
            success_count += 1
            if not parsed.dry_run:
                wrote = pipeline.write_outputs(result, parsed.output)
                if wrote:
                    # Find a runnable file for --run (prefer non-launch files)
                    for f in result.files:
                        if f.endswith('.py') and not f.endswith('_launch.py'):
                            package_name = pipeline._extract_package_name(result.ast)
                            last_generated_file = Path(parsed.output) / "ros2_ws" / "src" / package_name / package_name / f
                            break
                else:
                    print(format_result(result, file_path))
                    print()
                    success_count -= 1
                    failure_count += 1
        else:
            failure_count += 1

    # Run if requested and successful
    if parsed.run and success_count > 0 and last_generated_file:
        if parsed.verbose:
            print(f"Running: {last_generated_file}")
        
        # Add project root to PYTHONPATH so nos runtime can be found
        env = os.environ.copy()
        project_root = str(Path(__file__).parent.parent.parent)
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = f"{project_root}{os.pathsep}{env['PYTHONPATH']}"
        else:
            env['PYTHONPATH'] = project_root
            
        try:
            # We use the current python interpreter to run the generated node
            subprocess.run([sys.executable, str(last_generated_file)], env=env, check=True)
        except KeyboardInterrupt:
            pass
        except subprocess.CalledProcessError as e:
            print(f"Error running node: {e}", file=sys.stderr)
            return 1

    # Summary
    if parsed.verbose:
        print(f"\nSummary: {success_count} succeeded, {failure_count} failed")

    return 0 if failure_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
