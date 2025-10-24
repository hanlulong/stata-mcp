#!/usr/bin/env node

/**
 * Restore the VS Code extension package files
 *
 * This script restores the original VS Code package.json and README.md
 * after npm publishing is complete.
 */

const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..', '..');

// File paths
const vscodePackageJson = path.join(rootDir, 'package.json');
const backupPackageJson = path.join(rootDir, 'package.json.vscode-backup');

const vscodeReadme = path.join(rootDir, 'README.md');
const backupReadme = path.join(rootDir, 'README.md.vscode-backup');

// Hidden README files to restore
const readmeZhCn = path.join(rootDir, 'README.zh-CN.md');
const readmeZhCnHidden = path.join(rootDir, '.README.zh-CN.md.hidden');
const readmeVscodeExtension = path.join(rootDir, 'README-VSCODE-EXTENSION.md');
const readmeVscodeExtensionHidden = path.join(rootDir, '.README-VSCODE-EXTENSION.md.hidden');
const readmeUpdateSummary = path.join(rootDir, 'README_UPDATE_SUMMARY.md');
const readmeUpdateSummaryHidden = path.join(rootDir, '.README_UPDATE_SUMMARY.md.hidden');

console.log('Restoring VS Code extension package files...\n');

try {
    // Restore package.json
    if (fs.existsSync(backupPackageJson)) {
        console.log('✓ Restoring package.json from backup');
        fs.copyFileSync(backupPackageJson, vscodePackageJson);
        fs.unlinkSync(backupPackageJson);
    } else {
        console.warn('⚠ Warning: No package.json backup found');
    }

    // Restore README.md
    if (fs.existsSync(backupReadme)) {
        console.log('✓ Restoring README.md from backup');
        fs.copyFileSync(backupReadme, vscodeReadme);
        fs.unlinkSync(backupReadme);
    } else {
        console.warn('⚠ Warning: No README.md backup found');
    }

    // Restore hidden README files
    if (fs.existsSync(readmeZhCnHidden)) {
        console.log('✓ Restoring README.zh-CN.md');
        fs.renameSync(readmeZhCnHidden, readmeZhCn);
    }
    if (fs.existsSync(readmeVscodeExtensionHidden)) {
        console.log('✓ Restoring README-VSCODE-EXTENSION.md');
        fs.renameSync(readmeVscodeExtensionHidden, readmeVscodeExtension);
    }
    if (fs.existsSync(readmeUpdateSummaryHidden)) {
        console.log('✓ Restoring README_UPDATE_SUMMARY.md');
        fs.renameSync(readmeUpdateSummaryHidden, readmeUpdateSummary);
    }

    console.log('\n✓ VS Code extension package files restored!');

} catch (error) {
    console.error('✗ Error restoring package:', error.message);
    process.exit(1);
}
