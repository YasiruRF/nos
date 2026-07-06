"""End-to-end compilation pipeline for NOS.

Orchestrates the complete compilation process from source file
to generated code.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
import hashlib
import json
import re
import subprocess

# ANTLR4 imports
from antlr4 import CommonTokenStream, InputStream, ParseTreeWalker
from antlr4.error.ErrorListener import ErrorListener

# Import generated ANTLR4 classes
from ..grammar.NOSLexer import NOSLexer
from ..grammar.NOSParser import NOSParser

from ..ast import nodes
from ..ast.builder import ASTBuilder
from ..semantic import SemanticAnalyzer, AnalysisResult
from ..codegen import PythonGenerator, LaunchTranspiler, GenerationOutput


class NOSSyntaxError(Exception):
    """Syntax error in NOS source.

    Attributes:
        errors: List of syntax error messages
    """
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


class NOSErrorListener(ErrorListener):
    """Custom error listener for ANTLR4 syntax errors."""

    def __init__(self):
        super().__init__()
        self.errors = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        error_msg = f"Syntax error at {line}:{column} - {msg}"
        self.errors.append(error_msg)


@dataclass
class CompilationResult:
    """Result of a compilation.

    Attributes:
        success: True if compilation succeeded
        files: Generated files (path -> content)
        errors: Compilation errors
        warnings: Compilation warnings
        ast: The parsed and validated AST
    """
    success: bool = False
    files: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    ast: Optional[nodes.ASTNode] = None


class CompilerPipeline:
    """End-to-end NOS compilation pipeline.

    Orchestrates:
    1. Source file parsing (using ANTLR4)
    2. AST construction
    3. Semantic analysis
    4. Code generation

    Usage:
        >>> pipeline = CompilerPipeline()
        >>> result = pipeline.compile_file("input.nos")
        >>> if result.success:
        ...     pipeline.write_outputs(result, "output_dir/")
        ...     print(f"Generated {len(result.files)} files")
        ... else:
        ...     for error in result.errors:
        ...         print(f"Error: {error}")

    Attributes:
        options: Compilation options dict
        verbose: Whether to print debug information
        target: Target language ('python' or 'cpp')
    """

    def __init__(self, options: Optional[Dict[str, Any]] = None):
        """Initialize the compiler pipeline.

        Args:
            options: Compilation options including:
                - target: 'python' or 'cpp' (default: 'python')
                - verbose: Print debug info
                - output_dir: Default output directory
        """
        self.options = options or {}
        self.verbose = self.options.get('verbose', False)
        self.target = self.options.get('target', 'python')
        self.auto_build = self.options.get('auto_build', True)
        self.build_cache = self.options.get('build_cache', True)

    def compile_file(self, file_path: str) -> CompilationResult:
        """Compile a single NOS source file.

        Args:
            file_path: Path to .nos, .node, or .interface file

        Returns:
            CompilationResult with generated files or errors

        Example:
            >>> pipeline = CompilerPipeline({'verbose': True})
            >>> result = pipeline.compile_file('my_node.node')
            >>> print(f"Success: {result.success}")
            >>> print(f"Files generated: {list(result.files.keys())}")
        """
        result = CompilationResult()

        try:
            # Step 1: Parse source file
            if self.verbose:
                print(f"Parsing: {file_path}")

            ast = self._parse_file(file_path)
            if ast is None:
                result.errors.append(f"Failed to parse: {file_path}")
                return result

            result.ast = ast

            # Step 2: Semantic analysis
            if self.verbose:
                print(f"Analyzing: {file_path}")

            analysis = self._analyze(ast)
            result.errors.extend([str(e) for e in analysis.errors])
            result.warnings.extend([str(w) for w in analysis.warnings])

            if not analysis.is_valid:
                return result

            # Step 3: Code generation
            if self.verbose:
                print(f"Generating: {file_path}")

            generated = self._generate(ast, analysis.symbol_table)
            result.files = generated.files

            if hasattr(generated, 'security_errors') and generated.security_errors:
                result.errors.extend(generated.security_errors)
                result.success = False
                return result

            result.success = True
            return result

        except Exception as e:
            result.errors.append(f"Compilation error: {str(e)}")
            if self.verbose:
                import traceback
                result.errors.append(traceback.format_exc())
            return result

    def compile_string(self, source: str, file_name: str = "<string>") -> CompilationResult:
        """Compile NOS source from a string.

        Args:
            source: NOS source code
            file_name: Name for error reporting

        Returns:
            CompilationResult with generated files or errors
        """
        result = CompilationResult()

        try:
            # Parse
            ast = self._parse_string(source, file_name)
            if ast is None:
                result.errors.append(f"Failed to parse: {file_name}")
                return result

            result.ast = ast

            # Analyze
            analysis = self._analyze(ast)
            result.errors.extend([str(e) for e in analysis.errors])
            result.warnings.extend([str(w) for w in analysis.warnings])

            if not analysis.is_valid:
                return result

            # Generate
            generated = self._generate(ast, analysis.symbol_table)
            result.files = generated.files

            if hasattr(generated, 'security_errors') and generated.security_errors:
                result.errors.extend(generated.security_errors)
                result.success = False
                return result

            result.success = True
            return result

        except Exception as e:
            result.errors.append(f"Compilation error: {str(e)}")
            return result

    def _parse_file(self, file_path: str) -> Optional[nodes.ASTNode]:
        """Parse a source file into AST using ANTLR4.

        Args:
            file_path: Path to .nos, .node, or .interface file

        Returns:
            Root AST node or None if parsing fails
        """
        path = Path(file_path)
        if not path.exists():
            return None

        try:
            source = path.read_text(encoding='utf-8')
            return self._parse_string(source, str(path))
        except Exception as e:
            if self.verbose:
                print(f"Error reading file {file_path}: {e}")
            return None

    def _parse_string(self, source: str, file_name: str) -> Optional[nodes.ASTNode]:
        """Parse source string into AST using ANTLR4.

        Args:
            source: NOS source code
            file_name: Name for error reporting

        Returns:
            Root AST node or None if parsing fails
        """
        try:
            # Create input stream from source
            input_stream = InputStream(source)

            # Create lexer with custom error listener
            lexer = NOSLexer(input_stream)
            error_listener = NOSErrorListener()
            lexer.removeErrorListeners()
            lexer.addErrorListener(error_listener)

            # Create token stream
            tokens = CommonTokenStream(lexer)

            # Create parser with custom error listener
            parser = NOSParser(tokens)
            parser.removeErrorListeners()
            parser.addErrorListener(error_listener)

            # Parse starting from the 'nosFile' rule
            parse_tree = parser.nosFile()

            # Check for syntax errors
            if error_listener.errors:
                raise NOSSyntaxError(error_listener.errors)

            # Convert parse tree to AST using ASTBuilder
            builder = ASTBuilder(file_name)
            ast = builder.visit(parse_tree)

            return ast

        except NOSSyntaxError:
            raise
        except Exception as e:
            if self.verbose:
                print(f"Parse error in {file_name}: {e}")
                import traceback
                traceback.print_exc()
            return None

    def _analyze(self, ast: nodes.ASTNode) -> AnalysisResult:
        """Run semantic analysis on AST."""
        analyzer = SemanticAnalyzer()
        return analyzer.analyze(ast)

    def _generate(self, ast: nodes.ASTNode, symbol_table: Any) -> GenerationOutput:
        """Generate target code from AST."""
        output = GenerationOutput()

        if self.target == 'python':
            # Generate Python nodes
            node_gen = PythonGenerator(self.options)
            node_output = node_gen.generate(ast, symbol_table)
            output.files.update(node_output.files)
            
            if hasattr(node_output, 'security_errors') and node_output.security_errors:
                output.security_errors = node_output.security_errors

            # Generate launch files
            launch_gen = LaunchTranspiler(self.options)
            launch_output = launch_gen.generate(ast, symbol_table)
            output.files.update(launch_output.files)

        elif self.target == 'cpp':
            # TODO: Implement C++ generator
            pass

        return output

    def write_outputs(self, result: CompilationResult, output_dir: str) -> bool:
        """Write generated files to output directory.

        Args:
            result: Compilation result with files
            output_dir: Target directory path

        Returns:
            True if all files written successfully
        """
        if not result.success:
            return False

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        try:
            if self.target == 'python':
                workspace_path = output_path / "ros2_ws"
                package_name = self._extract_package_name(result.ast)
                package_root = workspace_path / "src" / package_name

                self._generate_ros2_package_scaffold(package_root, package_name, result.files)
                self._write_ros2_sources(package_root, package_name, result.files)

                if self.auto_build:
                    fingerprint = self._compute_build_fingerprint(result.files, package_name)
                    if self._should_run_build(workspace_path, package_name, fingerprint):
                        self._run_colcon_build(workspace_path, package_name)
                        self._update_build_cache(workspace_path, package_name, fingerprint)
                    elif self.verbose:
                        print(f"  Build cache hit for package '{package_name}', skipping colcon build")
            else:
                for file_path, content in result.files.items():
                    full_path = output_path / file_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding='utf-8')
                    if self.verbose:
                        print(f"  Wrote: {full_path}")
            return True
        except Exception as e:
            result.errors.append(f"Failed to write output: {str(e)}")
            return False

    def _extract_package_name(self, ast: Optional[nodes.ASTNode]) -> str:
        """Extract a valid ROS2 package name from AST."""
        candidate = "nos_generated"

        if isinstance(ast, nodes.File):
            if ast.package and ast.package.name:
                candidate = ast.package.name
            elif ast.declarations:
                first_decl = ast.declarations[0]
                if hasattr(first_decl, 'name') and getattr(first_decl, 'name'):
                    candidate = getattr(first_decl, 'name')
        elif ast and hasattr(ast, 'name') and getattr(ast, 'name'):
            candidate = getattr(ast, 'name')

        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', candidate).lower()
        if not sanitized:
            sanitized = "nos_generated"
        if sanitized[0].isdigit():
            sanitized = f"nos_{sanitized}"
        return sanitized

    def _compute_build_fingerprint(self, files: Dict[str, str], package_name: str) -> str:
        """Compute deterministic hash for generated outputs used by build cache."""
        hasher = hashlib.sha256()
        hasher.update(package_name.encode('utf-8'))
        hasher.update(self.target.encode('utf-8'))

        for file_path in sorted(files.keys()):
            hasher.update(file_path.encode('utf-8'))
            hasher.update(files[file_path].encode('utf-8'))

        return hasher.hexdigest()

    def _build_cache_file(self, workspace_path: Path) -> Path:
        """Return build cache file path."""
        return workspace_path / ".nos_build_cache.json"

    def _load_build_cache(self, workspace_path: Path) -> Dict[str, str]:
        """Load build cache dictionary from disk."""
        cache_file = self._build_cache_file(workspace_path)
        if not cache_file.exists():
            return {}
        try:
            return json.loads(cache_file.read_text(encoding='utf-8'))
        except Exception:
            return {}

    def _update_build_cache(self, workspace_path: Path, package_name: str, fingerprint: str) -> None:
        """Persist successful build fingerprint to cache."""
        cache = self._load_build_cache(workspace_path)
        cache[package_name] = fingerprint
        cache_file = self._build_cache_file(workspace_path)
        cache_file.write_text(json.dumps(cache, indent=2), encoding='utf-8')

    def _should_run_build(self, workspace_path: Path, package_name: str, fingerprint: str) -> bool:
        """Determine whether colcon build is required."""
        if not self.build_cache:
            return True

        cache = self._load_build_cache(workspace_path)
        cached = cache.get(package_name)
        install_package = workspace_path / "install" / package_name
        return cached != fingerprint or not install_package.exists()

    def _run_colcon_build(self, workspace_path: Path, package_name: str) -> None:
        """Run colcon build for a single package."""
        if self.verbose:
            print(f"  Building ROS2 package '{package_name}' with colcon")

        cmd = ["colcon", "build", "--packages-select", package_name]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                check=False
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "colcon executable not found. Install ROS2/colcon or run with --no-build."
            ) from exc

        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            stdout = proc.stdout.strip()
            details = stderr or stdout or "Unknown colcon build failure"
            raise RuntimeError(f"colcon build failed for package '{package_name}': {details}")

        if self.verbose and proc.stdout:
            print(proc.stdout)

    def _generate_ros2_package_scaffold(self, package_root: Path, package_name: str, files: Dict[str, str]) -> None:
        """Generate minimal ament_python package scaffolding."""
        package_module_dir = package_root / package_name
        launch_dir = package_root / "launch"
        resource_dir = package_root / "resource"

        package_module_dir.mkdir(parents=True, exist_ok=True)
        launch_dir.mkdir(parents=True, exist_ok=True)
        resource_dir.mkdir(parents=True, exist_ok=True)

        entry_points = []
        for path in sorted(files.keys()):
            if path.endswith('.py') and not path.endswith('.launch.py'):
                module = Path(path).name
                if module.endswith('.py'):
                    module = module[:-3]
                entry_points.append(f"            '{module} = {package_name}.{module}:main',")

        entry_points_block = "\n".join(entry_points) if entry_points else ""

        package_xml = f"""<?xml version="1.0"?>
<package format="3">
  <name>{package_name}</name>
  <version>0.0.1</version>
  <description>Auto-generated from NOS</description>
  <maintainer email="nos@local">NOS</maintainer>
  <license>Apache-2.0</license>

  <buildtool_depend>ament_python</buildtool_depend>

  <exec_depend>rclpy</exec_depend>
  <exec_depend>nos</exec_depend>

  <export>
    <build_type>ament_python</build_type>
  </export>
</package>
"""

        setup_cfg = """[develop]
script_dir=$base/lib/{package}
[install]
install_scripts=$base/lib/{package}
""".format(package=package_name)

        # Get list of launch files directly from the output files
        launch_files = [Path(f).name for f in files.keys() if f.endswith('.launch.py')]
        launch_files_str = ", ".join([f"'launch/{f}'" for f in sorted(launch_files)])

        setup_py = f"""from setuptools import find_packages, setup

package_name = '{package_name}'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', [{launch_files_str}]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='NOS',
    maintainer_email='nos@local',
    description='Auto-generated ROS2 package from NOS',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={{
        'console_scripts': [
{entry_points_block}
        ],
    }},
)
"""

        (package_root / "package.xml").write_text(package_xml, encoding='utf-8')
        (package_root / "setup.cfg").write_text(setup_cfg, encoding='utf-8')
        (package_root / "setup.py").write_text(setup_py, encoding='utf-8')
        (resource_dir / package_name).write_text("", encoding='utf-8')

        init_file = package_module_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text("", encoding='utf-8')

    def _write_ros2_sources(self, package_root: Path, package_name: str, files: Dict[str, str]) -> None:
        """Write generated Python and launch files into ROS2 package layout."""
        package_module_dir = package_root / package_name
        launch_dir = package_root / "launch"

        for file_path, content in files.items():
            rel_path = Path(file_path)
            if file_path.endswith('.launch.py'):
                target = launch_dir / rel_path.name
            else:
                target = package_module_dir / rel_path.name

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
            if self.verbose:
                print(f"  Wrote: {target}")

    def compile_multiple(self, file_paths: List[str]) -> Dict[str, CompilationResult]:
        """Compile multiple files and return results.

        Args:
            file_paths: List of source file paths

        Returns:
            Dictionary mapping file paths to compilation results
        """
        results = {}
        for path in file_paths:
            results[path] = self.compile_file(path)
        return results
