#!/usr/bin/env node

import { program } from "commander";

import { compileSample } from "./compile";

program
  .command("compile <sample-directory> <data-file> <output-directory>")
  .option("-p, --project", "Generate project file")
  .action(compileSample);

program.parse();
