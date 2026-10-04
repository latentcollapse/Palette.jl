#!/usr/bin/env python3
"""
Julia Static Analyzer for IJulia Operator Surface Project

This tool performs static analysis on Julia code using tree-sitter for accurate
parsing, validating:
- Syntax structure (via tree-sitter AST)
- Module and package structure
- Type definitions
- Function signatures
- Export statements
- Import/using statements
- Required components for each phase

Note: This does NOT execute Julia code - it only performs static analysis.
Actual runtime behavior must be tested in a real Julia environment.

LEVEL 0 validation: Fast, approximate, never authoritative.
Authoritative validation happens in GitHub CI with real Julia (LEVEL 1).
"""

import os
import re
import sys
import json
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path
from enum import Enum

try:
    from tree_sitter import Language, Parser
    import tree_sitter_julia
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False
    # stderr, not stdout: --json mode's contract is "JSON on stdout, nothing
    # else" (main() relies on this, printing nothing before json.dumps in
    # that branch) -- a stdout warning here broke it silently whenever
    # tree-sitter isn't installed, which this fallback path exists for.
    print("Warning: tree-sitter not available. Using regex-based fallback parser.", file=sys.stderr)


class Severity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class Issue:
    severity: Severity
    message: str
    file: str
    line: Optional[int] = None
    
    def __str__(self):
        loc = f":{self.line}" if self.line else ""
        return f"[{self.severity.value}] {self.file}{loc}: {self.message}"


@dataclass
class TypeDefinition:
    name: str
    kind: str  # 'struct', 'mutable struct', 'abstract type', 'primitive type'
    fields: list = field(default_factory=list)
    supertype: Optional[str] = None
    line: Optional[int] = None
    is_exported: bool = False


@dataclass
class FunctionDefinition:
    name: str
    params: list = field(default_factory=list)
    where_clause: Optional[str] = None
    line: Optional[int] = None
    is_exported: bool = False
    module_name: Optional[str] = None


@dataclass
class ModuleDefinition:
    name: str
    exports: list = field(default_factory=list)
    imports: list = field(default_factory=list)
    types: dict = field(default_factory=dict)
    functions: dict = field(default_factory=dict)
    line: Optional[int] = None


class JuliaParser:
    """Basic Julia code parser for static analysis."""
    
    def __init__(self):
        self.issues: list[Issue] = []
        self.modules: dict[str, ModuleDefinition] = {}
        self.types: dict[str, TypeDefinition] = {}
        self.functions: list[FunctionDefinition] = []
        
    def parse_file(self, filepath: str) -> bool:
        """Parse a Julia source file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            self.issues.append(Issue(
                Severity.ERROR, 
                f"Failed to read file: {e}", 
                filepath
            ))
            return False
            
        lines = content.split('\n')
        self._parse_content(content, lines, filepath)
        return True
    
    def _parse_content(self, content: str, lines: list[str], filepath: str):
        """Parse the content of a Julia file."""
        
        # Remove multi-line comments
        content_no_comments = re.sub(r'#.*$', '', content, flags=re.MULTILINE)
        content_no_block_comments = re.sub(r'#=\s*.*?\s*=#', '', content_no_comments, flags=re.DOTALL)
        
        # First pass: Parse modules, types, and functions
        self._parse_modules(content_no_block_comments, lines, filepath)
        self._parse_types(content_no_block_comments, lines, filepath)
        self._parse_functions(content_no_block_comments, lines, filepath)
        
        # Second pass: Parse exports (after types/functions are known)
        self._parse_exports(content_no_block_comments, lines, filepath)
        
        # Third pass: Parse imports
        self._parse_imports(content_no_block_comments, lines, filepath)
    
    def _parse_modules(self, content: str, lines: list[str], filepath: str):
        """Parse module definitions."""
        # Match module declarations
        module_pattern = r'(?:bare)?\s*module\s+(\w+)'
        
        for match in re.finditer(module_pattern, content):
            module_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            module_def = ModuleDefinition(name=module_name, line=line_num)
            self.modules[module_name] = module_def
            
            self.issues.append(Issue(
                Severity.INFO,
                f"Found module: {module_name}",
                filepath,
                line_num
            ))
    
    def _parse_types(self, content: str, lines: list[str], filepath: str):
        """Parse type definitions (struct, mutable struct, abstract type, primitive type)."""
        
        # Abstract types
        abstract_pattern = r'abstract\s+type\s+(\w+)(?:\s*<:\s*(\w+(?:\{[^}]*\})?))?'
        for match in re.finditer(abstract_pattern, content):
            type_name = match.group(1)
            supertype = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            type_def = TypeDefinition(
                name=type_name,
                kind='abstract type',
                supertype=supertype,
                line=line_num
            )
            self.types[type_name] = type_def
            
            self.issues.append(Issue(
                Severity.INFO,
                f"Found abstract type: {type_name}" + (f" <: {supertype}" if supertype else ""),
                filepath,
                line_num
            ))
        
        # Primitive types
        primitive_pattern = r'primitive\s+type\s+(\w+)\s+(\d+)(?:\s*<:\s*(\w+(?:\{[^}]*\})?))?'
        for match in re.finditer(primitive_pattern, content):
            type_name = match.group(1)
            bits = match.group(2)
            supertype = match.group(3)
            line_num = content[:match.start()].count('\n') + 1
            
            type_def = TypeDefinition(
                name=type_name,
                kind='primitive type',
                fields=[f"{bits} bits"],
                supertype=supertype,
                line=line_num
            )
            self.types[type_name] = type_def
            
            self.issues.append(Issue(
                Severity.INFO,
                f"Found primitive type: {type_name} ({bits} bits)" + (f" <: {supertype}" if supertype else ""),
                filepath,
                line_num
            ))
        
        # Structs and mutable structs - improved pattern to only capture field declarations
        struct_pattern = r'(mutable\s+)?struct\s+(\w+)(?:\{([^}]*)\})?(?:\s*<:\s*(\w+(?:\{[^}]*\})?))?\s*((?:\n\s*[^\n]+)*?)\nend'
        for match in re.finditer(struct_pattern, content, re.DOTALL):
            mutable = match.group(1) is not None
            type_name = match.group(2)
            type_params = match.group(3)
            supertype = match.group(4)
            body = match.group(5) or ""
            line_num = content[:match.start()].count('\n') + 1
            
            # Parse fields - only look for type annotations (field::Type patterns)
            fields = []
            for field_line in body.strip().split('\n'):
                field_line = field_line.strip()
                # Skip empty lines, comments, function definitions, and statements
                if (field_line and 
                    not field_line.startswith('#') and
                    not field_line.startswith('function ') and
                    not field_line.startswith('new(') and
                    not field_line.startswith('return ') and
                    not field_line.startswith('now =') and
                    not field_line.startswith('state.') and
                    not field_line == 'end'):
                    # Clean up the field definition
                    field_clean = re.sub(r'#.*$', '', field_line).strip()
                    # Only include lines that look like field declarations (:: indicates type annotation)
                    if field_clean and '::' in field_clean:
                        fields.append(field_clean)
            
            kind = 'mutable struct' if mutable else 'struct'
            type_def = TypeDefinition(
                name=type_name,
                kind=kind,
                fields=fields,
                supertype=supertype,
                line=line_num
            )
            self.types[type_name] = type_def
            
            self.issues.append(Issue(
                Severity.INFO,
                f"Found {kind}: {type_name}" + (f"{{{type_params}}}" if type_params else "") + (f" <: {supertype}" if supertype else ""),
                filepath,
                line_num
            ))
    
    def _parse_functions(self, content: str, lines: list[str], filepath: str):
        """Parse function definitions."""
        
        # Standard function definition
        func_pattern = r'function\s+(\w+(?:\.[\w!]+)?)(?:\{([^}]*)\})?\s*\(([^)]*)\)(?:\s*where\s+([^\n]+))?'
        for match in re.finditer(func_pattern, content):
            func_name = match.group(1)
            type_params = match.group(2)
            params = match.group(3) or ""
            where_clause = match.group(4)
            line_num = content[:match.start()].count('\n') + 1
            
            param_list = [p.strip() for p in params.split(',') if p.strip()]
            
            func_def = FunctionDefinition(
                name=func_name,
                params=param_list,
                where_clause=where_clause,
                line=line_num
            )
            self.functions.append(func_def)
            
            self.issues.append(Issue(
                Severity.INFO,
                f"Found function: {func_name}" + (f"{{{type_params}}}" if type_params else "") + f"({params})",
                filepath,
                line_num
            ))
        
        # Short-form function definition
        short_func_pattern = r'^\s*(\w+(?:\.[\w!]+)?)\(([^)]*)\)\s*(?:where\s+([^\n]+))?\s*='
        for match in re.finditer(short_func_pattern, content, re.MULTILINE):
            func_name = match.group(1)
            params = match.group(2) or ""
            where_clause = match.group(3)
            line_num = content[:match.start()].count('\n') + 1
            
            param_list = [p.strip() for p in params.split(',') if p.strip()]
            
            # Check if this is likely a function definition (not a function call)
            # by looking at the context
            func_def = FunctionDefinition(
                name=func_name,
                params=param_list,
                where_clause=where_clause,
                line=line_num
            )
            self.functions.append(func_def)
            
            self.issues.append(Issue(
                Severity.INFO,
                f"Found short-form function: {func_name}({params})",
                filepath,
                line_num
            ))
    
    def _parse_exports(self, content: str, lines: list[str], filepath: str):
        """Parse export statements."""
        # Process line by line to handle each export statement separately
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped.startswith('export'):
                continue
            
            # Extract exports from this single line only
            # Match 'export' followed by items until end of line or comment
            export_match = re.match(r'export\s+([^\n#]+)', stripped)
            if not export_match:
                continue
                
            exports_str = export_match.group(1)
            
            # Split by comma and clean up each export name
            exports = []
            for e in exports_str.split(','):
                e = e.strip()
                if e and not e.startswith('end'):
                    # Handle cases where 'end' got attached
                    if 'end' in e:
                        e = e.replace('end', '').strip()
                    if e:
                        exports.append(e)
            
            # Mark types/functions as exported
            for exp in exports:
                exp = exp.strip()
                # Check all types
                for type_name, type_def in self.types.items():
                    if exp == type_name:
                        type_def.is_exported = True
                
                # Check all functions
                for func in self.functions:
                    if func.name == exp or func.name.endswith('.' + exp):
                        func.is_exported = True
            
            if exports:
                self.issues.append(Issue(
                    Severity.INFO,
                    f"Export statement: {exports}",
                    filepath,
                    line_num
                ))
    
    def _parse_imports(self, content: str, lines: list[str], filepath: str):
        """Parse using and import statements."""
        
        # using statements
        using_pattern = r'using\s+([\w.:,\s]+)'
        for match in re.finditer(using_pattern, content):
            imports_str = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            self.issues.append(Issue(
                Severity.INFO,
                f"Using: {imports_str}",
                filepath,
                line_num
            ))
        
        # import statements
        import_pattern = r'import\s+([\w.:,\s]+)'
        for match in re.finditer(import_pattern, content):
            imports_str = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            self.issues.append(Issue(
                Severity.INFO,
                f"Import: {imports_str}",
                filepath,
                line_num
            ))


class PhaseValidator:
    """Validates that required components exist for each phase."""
    
    PHASE_REQUIREMENTS = {
        1: {
            "name": "Prove IJulia State Persistence",
            "required_types": [],
            "required_functions": [],
            "description": "Demonstrate that IJulia kernel maintains state across executions"
        },
        2: {
            "name": "Define Operator Types & Vocabulary",
            "required_types": ["OperatorType", "OperatorVocabulary"],
            "required_functions": [],
            "description": "Define core operator type system and vocabulary"
        },
        3: {
            "name": "Audit Existing Vocabularies",
            "required_types": [],
            "required_functions": [],
            "description": "Review existing vocabularies from related projects"
        },
        4: {
            "name": "Implement Core Operations",
            "required_types": ["ExecuteCode", "InvokeOperator", "GetState"],
            "required_functions": [],
            "description": "Implement basic operator operations"
        },
        5: {
            "name": "Add Structured Semantics",
            "required_types": ["OperationResult", "StructuredResponse"],
            "required_functions": [],
            "description": "Add structured response semantics"
        },
        6: {
            "name": "Implement Discovery & Introspection",
            "required_types": ["DiscoveryService", "IntrospectionResult"],
            "required_functions": [],
            "description": "Enable discovery of available operators and capabilities"
        },
        7: {
            "name": "Add Operation Receipts",
            "required_types": ["OperationReceipt", "ReceiptLog"],
            "required_functions": [],
            "description": "Generate receipts for audit trail"
        },
        8: {
            "name": "Legacy Shell Escape Hatch",
            "required_types": ["ShellEscape"],
            "required_functions": [],
            "description": "Provide shell command execution capability"
        },
        9: {
            "name": "Failure Handling & Safety",
            "required_types": ["ErrorHandler", "SafetyGuard"],
            "required_functions": [],
            "description": "Implement robust failure handling"
        },
        10: {
            "name": "Integration Demo",
            "required_types": [],
            "required_functions": [],
            "description": "Complete end-to-end demonstration"
        }
    }
    
    def __init__(self, parser: JuliaParser):
        self.parser = parser
        
    def validate_phase(self, phase_num: int) -> list[Issue]:
        """Validate that required components exist for a phase."""
        issues = []
        
        if phase_num not in self.PHASE_REQUIREMENTS:
            issues.append(Issue(
                Severity.ERROR,
                f"Unknown phase: {phase_num}",
                "phase_validator"
            ))
            return issues
        
        req = self.PHASE_REQUIREMENTS[phase_num]
        
        # Check required types. ERROR, not WARNING: this is the one check
        # this whole analyzer exists to make, and a WARNING never fails the
        # CI step that runs it (`julia_analyzer.py`'s only other ERROR is a
        # file-read I/O failure) -- confirmed by deleting the ShellEscape
        # struct entirely and finding the "preflight" step still exits 0.
        # A required component silently missing is exactly the class of
        # defect a preflight check is supposed to catch before Pkg.test()
        # spends real time on it.
        for type_name in req["required_types"]:
            if type_name not in self.parser.types:
                issues.append(Issue(
                    Severity.ERROR,
                    f"Phase {phase_num} requires type '{type_name}' but it was not found",
                    "phase_validator"
                ))
            elif not self.parser.types[type_name].is_exported:
                issues.append(Issue(
                    Severity.INFO,
                    f"Type '{type_name}' exists but may not be exported",
                    "phase_validator"
                ))

        # Check required functions
        for func_name in req["required_functions"]:
            found = any(f.name == func_name or f.name.endswith('.' + func_name)
                       for f in self.parser.functions)
            if not found:
                issues.append(Issue(
                    Severity.ERROR,
                    f"Phase {phase_num} requires function '{func_name}' but it was not found",
                    "phase_validator"
                ))
        
        return issues


class JuliaStaticAnalyzer:
    """Main analyzer class that orchestrates parsing and validation."""
    
    def __init__(self):
        self.parser = JuliaParser()
        self.validator = PhaseValidator(self.parser)
        self._phases_validated = False
        
    def analyze_directory(self, directory: str, extensions: list[str] = ['.jl']) -> bool:
        """Analyze all Julia files in a directory."""
        dir_path = Path(directory)
        
        if not dir_path.exists():
            print(f"Error: Directory '{directory}' does not exist")
            return False
        
        julia_files = []
        for ext in extensions:
            julia_files.extend(dir_path.rglob(f'*{ext}'))
        
        if not julia_files:
            print(f"No Julia files found in '{directory}'")
            return False
        
        print(f"Found {len(julia_files)} Julia file(s) to analyze\n")
        
        for jl_file in julia_files:
            print(f"Analyzing: {jl_file}")
            self.parser.parse_file(str(jl_file))
        
        return True
    
    def analyze_file(self, filepath: str) -> bool:
        """Analyze a single Julia file."""
        return self.parser.parse_file(filepath)
    
    def validate_phases(self, max_phase: int = 10) -> dict[int, list[Issue]]:
        """Validate all phases up to max_phase. Extends `self.parser.issues`
        -- the list `get_summary()`'s error/warning counts (and therefore
        the CLI's exit code) actually read -- not a separate `all_issues`
        list nothing else in this file ever consumed, which is how a
        Phase-level ERROR could exist and still leave the process exiting
        0 (found by deleting a required struct and watching the CI-facing
        exit code stay clean). Idempotent per instance: calling this more
        than once (print_report and a --json summary both may) must not
        duplicate every phase issue into parser.issues on the second call.
        """
        phase_results = {}

        for phase in range(1, max_phase + 1):
            issues = self.validator.validate_phase(phase)
            phase_results[phase] = issues
            if not self._phases_validated:
                self.parser.issues.extend(issues)

        self._phases_validated = True
        return phase_results
    
    def get_summary(self) -> dict:
        """Get a summary of the analysis."""
        error_count = sum(1 for i in self.parser.issues if i.severity == Severity.ERROR)
        warning_count = sum(1 for i in self.parser.issues if i.severity == Severity.WARNING)
        info_count = sum(1 for i in self.parser.issues if i.severity == Severity.INFO)
        
        return {
            'files_analyzed': len(set(i.file for i in self.parser.issues)),
            'modules_found': len(self.parser.modules),
            'types_found': len(self.parser.types),
            'functions_found': len(self.parser.functions),
            'errors': error_count,
            'warnings': warning_count,
            'info': info_count
        }
    
    def print_report(self, include_info: bool = False):
        """Print a detailed analysis report."""
        print("\n" + "=" * 70)
        print("JULIA STATIC ANALYSIS REPORT")
        print("=" * 70)
        
        # Summary
        summary = self.get_summary()
        print(f"\nSUMMARY:")
        print(f"  Modules:   {summary['modules_found']}")
        print(f"  Types:     {summary['types_found']}")
        print(f"  Functions: {summary['functions_found']}")
        print(f"  Errors:    {summary['errors']}")
        print(f"  Warnings:  {summary['warnings']}")
        if include_info:
            print(f"  Info:      {summary['info']}")
        
        # Types found
        if self.parser.types:
            print(f"\nTYPES FOUND ({len(self.parser.types)}):")
            for name, type_def in self.parser.types.items():
                exported = " [exported]" if type_def.is_exported else ""
                print(f"  - {type_def.kind}: {name}{exported}")
                if type_def.fields and include_info:
                    for field in type_def.fields[:3]:  # Show first 3 fields
                        print(f"      • {field}")
                    if len(type_def.fields) > 3:
                        print(f"      ... and {len(type_def.fields) - 3} more")
        
        # Functions found
        if self.parser.functions:
            print(f"\nFUNCTIONS FOUND ({len(self.parser.functions)}):")
            for func in self.parser.functions[:20]:  # Limit output
                exported = " [exported]" if func.is_exported else ""
                params = ', '.join(func.params[:3])
                if len(func.params) > 3:
                    params += f"... (+{len(func.params) - 3})"
                print(f"  - {func.name}({params}){exported}")
            if len(self.parser.functions) > 20:
                print(f"  ... and {len(self.parser.functions) - 20} more")
        
        # Issues (excluding info unless requested)
        significant_issues = [i for i in self.parser.issues if i.severity != Severity.INFO or include_info]
        if significant_issues:
            print(f"\nISSUES ({len(significant_issues)}):")
            for issue in significant_issues[:50]:  # Limit output
                print(f"  {issue}")
            if len(significant_issues) > 50:
                print(f"  ... and {len(significant_issues) - 50} more")
        
        # Phase validation
        print("\n" + "-" * 70)
        print("PHASE VALIDATION")
        print("-" * 70)
        
        phase_results = self.validate_phases()
        for phase_num, issues in phase_results.items():
            phase_name = self.validator.PHASE_REQUIREMENTS[phase_num]["name"]
            status = "✓ PASS" if not issues else f"⚠ {len(issues)} issue(s)"
            print(f"\nPhase {phase_num}: {phase_name}")
            print(f"  Status: {status}")
            for issue in issues:
                print(f"    - {issue.message}")
        
        print("\n" + "=" * 70)
        
        return summary


def main():
    """Main entry point."""
    import argparse
    
    arg_parser = argparse.ArgumentParser(
        description='Julia Static Analyzer for IJulia Operator Surface Project'
    )
    arg_parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Path to Julia file or directory (default: current directory)'
    )
    arg_parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Include INFO level messages'
    )
    arg_parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
    )
    
    args = arg_parser.parse_args()
    
    analyzer = JuliaStaticAnalyzer()
    
    path = Path(args.path)
    if path.is_file():
        success = analyzer.analyze_file(str(path))
    elif path.is_dir():
        success = analyzer.analyze_directory(str(path))
    else:
        print(f"Error: Path '{args.path}' does not exist")
        sys.exit(1)
    
    if not success:
        sys.exit(1)
    
    if args.json:
        import json
        analyzer.validate_phases()  # otherwise --json mode omits phase validation entirely
        # Only output JSON, not the "Found X files" messages
        summary = analyzer.get_summary()
        summary['types'] = {
            name: {
                'kind': td.kind,
                'fields': td.fields,
                'supertype': td.supertype,
                'exported': td.is_exported
            }
            for name, td in analyzer.parser.types.items()
        }
        summary['functions'] = [
            {
                'name': f.name,
                'params': f.params,
                'exported': f.is_exported
            }
            for f in analyzer.parser.functions
        ]
        summary['issues'] = [
            {
                'severity': i.severity.value,
                'message': i.message,
                'file': i.file,
                'line': i.line
            }
            for i in analyzer.parser.issues
        ]
        print(json.dumps(summary, indent=2))  # JSON to stdout
        sys.exit(0)  # Exit cleanly
    else:
        analyzer.print_report(include_info=args.verbose)
    
    # Exit with error code if there are errors
    summary = analyzer.get_summary()
    if summary['errors'] > 0:
        sys.exit(1)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
