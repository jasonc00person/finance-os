#!/usr/bin/env node

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { PROJECT_ROOT, SEQUENCE_API_KEY, SEQUENCE_BASE_URL } from './config.js';
import { SequenceClient } from './sequence-client.js';
import {
  findAccount,
  formatAccountDetails,
  formatAccounts,
  formatRuleExecutions,
  formatRules,
  formatTransfers,
  sanitizeAccount,
  summarizeAccounts,
} from './formatters.js';

if (!SEQUENCE_API_KEY) {
  console.error('Error: SEQUENCE_API_KEY environment variable is required. Put it in the project .env');
  process.exit(1);
}

const sequence = new SequenceClient(SEQUENCE_API_KEY, SEQUENCE_BASE_URL);

const server = new McpServer({
  name: 'sequence-finance-mcp',
  version: '0.1.0',
});

server.tool(
  'list_sequence_accounts',
  {
    type: z.enum(['INCOME_SOURCE', 'POD', 'EXTERNAL_ACCOUNT']).optional().describe('Optional account type filter.'),
    include_balances: z.boolean().optional().describe('Fetch full account details with balances. Slower, but needed for balance data. Defaults to false.'),
  },
  async ({ type, include_balances }) => {
    if (include_balances) {
      const result = await sequence.listAccountDetails({ type });
      return {
        content: [{ type: 'text', text: formatAccountDetails(result.accounts, result.requestId) }],
      };
    }

    return {
      content: [{ type: 'text', text: formatAccounts((await sequence.listAccounts({ type })).accounts) }],
    };
  }
);

server.tool(
  'get_sequence_account',
  {
    query: z.string().describe('Account id or part of the account name.'),
  },
  async ({ query }) => {
    const result = await sequence.listAccounts();
    const matches = findAccount(result.accounts, query);

    if (matches.length === 0) {
      return {
        content: [{ type: 'text', text: `No Sequence account matched "${query}".` }],
        isError: true,
      };
    }

    const detailed = await Promise.all(matches.map((account) => sequence.getAccount(account.id).then((item) => item.account)));
    return {
      content: [{ type: 'text', text: formatAccountDetails(detailed, result.requestId) }],
    };
  }
);

server.tool(
  'summarize_sequence_balances',
  {},
  async () => {
    const result = await sequence.listAccountDetails();
    return {
      content: [{ type: 'text', text: summarizeAccounts(result.accounts, result.requestId) }],
    };
  }
);

server.tool(
  'list_sequence_transfers',
  {
    account_id: z.string().describe('Sequence account ID. The API requires transfers to be listed by account.'),
    account_role: z.enum(['source', 'destination', 'either']).optional().describe('How the account ID is matched. Defaults to either.'),
    direction: z.enum(['MONEY_IN', 'MONEY_OUT', 'INTERNAL']).optional().describe('Optional direction filter.'),
    status: z.enum(['PENDING_APPROVAL', 'PROCESSING', 'PENDING', 'COMPLETE', 'INCOMPLETE', 'ERROR', 'CANCELLED']).optional().describe('Optional status filter.'),
    origin: z.enum(['DIRECT_DEPOSIT', 'CHECK_DEPOSIT', 'CASHBACK', 'USER_PULL', 'RULE', 'USER', 'EXTERNAL_PULL']).optional().describe('Optional origin filter.'),
    from: z.string().optional().describe('Return transfers created at or after this ISO timestamp.'),
    to: z.string().optional().describe('Return transfers created at or before this ISO timestamp.'),
    rule_execution_id: z.string().optional().describe('Optional rule execution ID filter.'),
    page_size: z.number().min(1).max(100).optional().describe('Page size, max 100. Defaults to 50.'),
  },
  async ({ account_id, account_role, direction, status, origin, from, to, rule_execution_id, page_size }) => {
    const result = await sequence.listTransfers(account_id, {
      accountRole: account_role,
      direction,
      status,
      origin,
      from,
      to,
      rule_execution_id,
      pageSize: page_size,
    });

    return {
      content: [{ type: 'text', text: formatTransfers(result.transfers, result.requestId) }],
    };
  }
);

server.tool(
  'get_sequence_transfer',
  {
    transfer_id: z.string().describe('Sequence transfer ID.'),
  },
  async ({ transfer_id }) => {
    const result = await sequence.getTransfer(transfer_id);
    return {
      content: [{ type: 'text', text: formatTransfers([result.transfer], result.requestId) }],
    };
  }
);

server.tool(
  'list_sequence_rules',
  {
    source_id: z.string().optional().describe('Optional source account ID filter.'),
  },
  async ({ source_id }) => {
    const result = await sequence.listRules({ sourceId: source_id });
    return {
      content: [{ type: 'text', text: formatRules(result.rules, result.requestId) }],
    };
  }
);

server.tool(
  'list_sequence_rule_executions',
  {
    rule_id: z.string().describe('Sequence rule ID.'),
    status: z.enum(['EXECUTED', 'PARTIAL', 'FAILED', 'IN_PROGRESS']).optional().describe('Optional execution status filter.'),
    trigger_type: z.enum(['MANUAL', 'SCHEDULED', 'ON_FUNDS_TRANSFERRED']).optional().describe('Optional trigger type filter.'),
    from: z.string().optional().describe('Return executions created at or after this ISO timestamp.'),
    to: z.string().optional().describe('Return executions created at or before this ISO timestamp.'),
    page_size: z.number().min(1).max(100).optional().describe('Page size, max 100. Defaults to 50.'),
  },
  async ({ rule_id, status, trigger_type, from, to, page_size }) => {
    const result = await sequence.listRuleExecutions(rule_id, {
      status,
      triggerType: trigger_type,
      from,
      to,
      pageSize: page_size,
    });

    return {
      content: [{ type: 'text', text: formatRuleExecutions(result.executions, result.requestId) }],
    };
  }
);

server.tool(
  'save_sequence_snapshot',
  {
    output_dir: z.string().optional().describe('Directory for snapshot files. Defaults to finance/sequence-snapshots.'),
  },
  async ({ output_dir }) => {
    const result = await sequence.listAccountDetails();
    const targetDir = output_dir || path.join(PROJECT_ROOT, 'sequence-snapshots');
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const jsonPath = path.join(targetDir, `${timestamp}-sequence-accounts.json`);
    const markdownPath = path.join(targetDir, `${timestamp}-sequence-accounts.md`);

    await fs.mkdir(targetDir, { recursive: true });
    await fs.writeFile(jsonPath, JSON.stringify({
      requestId: result.requestId,
      accounts: result.accounts.map(sanitizeAccount),
    }, null, 2), 'utf8');
    await fs.writeFile(markdownPath, formatAccountDetails(result.accounts, result.requestId), 'utf8');

    return {
      content: [{
        type: 'text',
        text: `Saved Sequence snapshot:\n- ${jsonPath}\n- ${markdownPath}`,
      }],
    };
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

process.on('uncaughtException', (error) => {
  console.error('Uncaught exception:', error.message);
  process.exit(1);
});

process.on('unhandledRejection', (reason) => {
  console.error('Unhandled rejection:', reason instanceof Error ? reason.message : reason);
  process.exit(1);
});

main().catch((error) => {
  console.error('Server initialization failed:', error.message);
  process.exit(1);
});
