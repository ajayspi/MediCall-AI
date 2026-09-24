import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next";

export default defineConfig([
  ...nextVitals,
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "node_modules/**",
    "public/**",
    "package-lock.json",
  ]),
]);