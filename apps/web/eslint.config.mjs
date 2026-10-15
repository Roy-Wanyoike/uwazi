import { defineConfig, globalIgnores } from "eslint/config";
import tseslint from "typescript-eslint";

export default defineConfig(
  globalIgnores([".next/**", "next-env.d.ts"]),
  tseslint.configs.recommended,
);
