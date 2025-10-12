#!/usr/bin/env node

/**
 * Prepare the package for npm publishing
 *
 * This script:
 * 1. Backs up the VS Code extension package.json
 * 2. Copies package-standalone.json to package.json
 * 3. Copies README-standalone.md to README.md
 */

const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');

// File paths
const vscodePackageJson = path.join(rootDir, 'package.json');
const standalonePackageJson = path.join(rootDir, 'package-standalone.json');
const backupPackageJson = path.join(rootDir, 'package.json.vscode-backup');

const vscodeReadme = path.join(rootDir, 'README.md');
const standaloneReadme = path.join(rootDir, 'README-standalone.md');
const backupReadme = path.join(rootDir, 'README.md.vscode-backup');

// Other README files to temporarily hide
const readmeZhCn = path.join(rootDir, 'README.zh-CN.md');
const readmeZhCnHidden = path.join(rootDir, '.README.zh-CN.md.hidden');
const readmeVscodeExtension = path.join(rootDir, 'README-VSCODE-EXTENSION.md');
const readmeVscodeExtensionHidden = path.join(rootDir, '.README-VSCODE-EXTENSION.md.hidden');
const readmeUpdateSummary = path.join(rootDir, 'README_UPDATE_SUMMARY.md');
const readmeUpdateSummaryHidden = path.join(rootDir, '.README_UPDATE_SUMMARY.md.hidden');

console.log('Preparing package for npm publishing...\n');

try {
    // Backup VS Code package.json
    if (fs.existsSync(vscodePackageJson)) {
        console.log('✓ Backing up VS Code package.json');
        fs.copyFileSync(vscodePackageJson, backupPackageJson);
    }

    // Copy standalone package.json
    if (fs.existsSync(standalonePackageJson)) {
        console.log('✓ Copying package-standalone.json to package.json');
        fs.copyFileSync(standalonePackageJson, vscodePackageJson);
    } else {
        console.error('✗ Error: package-standalone.json not found');
        process.exit(1);
    }

    // Backup VS Code README.md if it exists
    if (fs.existsSync(vscodeReadme)) {
        console.log('✓ Backing up VS Code README.md');
        fs.copyFileSync(vscodeReadme, backupReadme);
    }

    // Copy standalone README
    if (fs.existsSync(standaloneReadme)) {
        console.log('✓ Copying README-standalone.md to README.md');
        fs.copyFileSync(standaloneReadme, vscodeReadme);
    } else {
        console.error('✗ Error: README-standalone.md not found');
        process.exit(1);
    }

    // Hide other README files to prevent npm from including them
    if (fs.existsSync(readmeZhCn)) {
        console.log('✓ Hiding README.zh-CN.md');
        fs.renameSync(readmeZhCn, readmeZhCnHidden);
    }
    if (fs.existsSync(readmeVscodeExtension)) {
        console.log('✓ Hiding README-VSCODE-EXTENSION.md');
        fs.renameSync(readmeVscodeExtension, readmeVscodeExtensionHidden);
    }
    if (fs.existsSync(readmeUpdateSummary)) {
        console.log('✓ Hiding README_UPDATE_SUMMARY.md');
        fs.renameSync(readmeUpdateSummary, readmeUpdateSummaryHidden);
    }

    console.log('\n✓ Package prepared for npm publishing!');
    console.log('\nNext steps:');
    console.log('1. Review the package contents: npm pack --dry-run');
    console.log('2. Test locally: npm link');
    console.log('3. Publish to npm: npm publish');
    console.log('4. Restore VS Code files: node scripts/restore-vscode-package.js');

} catch (error) {
    console.error('✗ Error preparing package:', error.message);
    process.exit(1);
}
