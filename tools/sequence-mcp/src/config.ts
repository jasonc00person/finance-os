import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '../../..');

dotenv.config({ path: path.join(projectRoot, '.env') });
dotenv.config();

export const PROJECT_ROOT = projectRoot;
export const SEQUENCE_BASE_URL = process.env.SEQUENCE_BASE_URL || 'https://api.getsequence.io/platform/v1';
export const SEQUENCE_API_KEY = (process.env.SEQUENCE_API_KEY || process.env.SEQUENCE_ACCESS_TOKEN)
  ?.trim()
  .replace(/^['"]|['"]$/g, '')
  .replace(/^Bearer\s+/i, '');
