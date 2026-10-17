import { SEQUENCE_API_KEY, SEQUENCE_BASE_URL } from './config.js';
import { SequenceClient } from './sequence-client.js';
import { summarizeAccounts } from './formatters.js';

if (!SEQUENCE_API_KEY) {
  console.error('SEQUENCE_API_KEY is missing. Add it to the project .env');
  process.exit(1);
}

const client = new SequenceClient(SEQUENCE_API_KEY, SEQUENCE_BASE_URL);
const result = await client.listAccountDetails();

console.log(summarizeAccounts(result.accounts, result.requestId));
