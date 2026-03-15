import os
import tempfile
import unittest

from nodus.runtime.diagnostics import LangRuntimeError
from nodus.runtime.module_loader import ModuleLoader
from nodus.tooling.loader import compile_source


class ImportContainmentTests(unittest.TestCase):
    def test_tooling_loader_blocks_escape(self):
        with tempfile.TemporaryDirectory() as root:
            app_dir = os.path.join(root, "app")
            os.makedirs(app_dir, exist_ok=True)
            main_path = os.path.join(app_dir, "main.nd")
            outside_dir = os.path.dirname(root)
            secret_path = os.path.join(outside_dir, "secret.nd")
            with open(secret_path, "w", encoding="utf-8") as handle:
                handle.write('print("secret")\n')
            with open(main_path, "w", encoding="utf-8") as handle:
                handle.write('import "../../secret.nd"\n')

            code = 'import "../../secret.nd"\n'
            import_state = {
                "loaded": set(),
                "loading": set(),
                "exports": {},
                "modules": {},
                "module_ids": {},
                "project_root": root,
            }

            with self.assertRaises(LangRuntimeError) as ctx:
                compile_source(code, source_path=main_path, import_state=import_state)
            self.assertEqual(ctx.exception.kind, "import")

    def test_runtime_loader_blocks_escape(self):
        with tempfile.TemporaryDirectory() as root:
            app_dir = os.path.join(root, "app")
            os.makedirs(app_dir, exist_ok=True)
            main_path = os.path.join(app_dir, "main.nd")
            outside_dir = os.path.dirname(root)
            secret_path = os.path.join(outside_dir, "secret.nd")
            with open(secret_path, "w", encoding="utf-8") as handle:
                handle.write('print("secret")\n')
            with open(main_path, "w", encoding="utf-8") as handle:
                handle.write('import "../../secret.nd"\n')

            loader = ModuleLoader(project_root=root)
            with self.assertRaises(LangRuntimeError) as ctx:
                loader.load_module_from_path(main_path)
            self.assertEqual(ctx.exception.kind, "import")


if __name__ == "__main__":
    unittest.main()
