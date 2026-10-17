import type {
  SequenceAccount,
  SequenceAccountSummary,
  SequenceRule,
  SequenceRuleExecution,
  SequenceTransfer,
} from './sequence-client.js';

export function dollars(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'unknown';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value);
}

export function cents(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'unknown';
  return dollars(value / 100);
}

export function accountBalanceInCents(account: SequenceAccount): number | null {
  return account.balance?.balanceInCents ?? null;
}

function accountMeta(account: SequenceAccountSummary): string {
  return [
    account.type,
    account.externalAccountType,
    account.institutionName,
  ].filter(Boolean).join(' / ');
}

export function sanitizeAccount(account: SequenceAccount): SequenceAccount {
  const { routingNumber: _routingNumber, bankAccountNumber: _bankAccountNumber, ...safe } = account;
  return safe;
}

export function formatAccounts(accounts: SequenceAccountSummary[], requestId?: string): string {
  const lines = ['# Sequence Accounts', ''];

  if (requestId) lines.push(`Request ID: \`${requestId}\``, '');

  if (accounts.length === 0) {
    lines.push('No accounts returned.');
  } else {
    for (const account of accounts) {
      const details = accountMeta(account);
      lines.push(`- **${account.name}** (${details}) - \`${account.id}\``);
    }
  }

  return lines.join('\n');
}

export function formatAccountDetails(accounts: SequenceAccount[], requestId?: string): string {
  const lines = ['# Sequence Account Details', ''];
  if (requestId) lines.push(`Request ID: \`${requestId}\``, '');

  if (accounts.length === 0) {
    lines.push('No accounts returned.');
    return lines.join('\n');
  }

  for (const account of accounts) {
    const balance = account.balance;
    const balanceError = balance?.error ? ` - balance error: ${balance.error}` : '';
    lines.push(`- **${account.name}** (${accountMeta(account)}) - ${cents(balance?.balanceInCents)} - \`${account.id}\`${balanceError}`);
    if (balance?.availableBalanceInCents !== null && balance?.availableBalanceInCents !== undefined) {
      lines.push(`  Available: ${cents(balance.availableBalanceInCents)}`);
    }
    if (balance?.lastStatementBalanceInCents !== null && balance?.lastStatementBalanceInCents !== undefined) {
      lines.push(`  Last statement: ${cents(balance.lastStatementBalanceInCents)}${balance.lastStatementDate ? ` on ${balance.lastStatementDate}` : ''}`);
    }
    if (balance?.nextPaymentMinimumInCents !== null && balance?.nextPaymentMinimumInCents !== undefined) {
      lines.push(`  Minimum due: ${cents(balance.nextPaymentMinimumInCents)}${balance.nextPaymentDueDate ? ` by ${balance.nextPaymentDueDate}` : ''}`);
    }
    if (balance?.balanceLastUpdatedAt) {
      lines.push(`  Updated: ${balance.balanceLastUpdatedAt}`);
    }
  }

  return lines.join('\n');
}

export function summarizeAccounts(accounts: SequenceAccount[], requestId?: string): string {
  const byType = new Map<string, { count: number; total: number }>();
  let total = 0;
  let knownBalanceCount = 0;
  const balanceErrors: string[] = [];

  for (const account of accounts) {
    const value = accountBalanceInCents(account);
    const type = account.externalAccountType ? `${account.type} / ${account.externalAccountType}` : account.type;
    const current = byType.get(type) || { count: 0, total: 0 };
    current.count += 1;

    if (typeof value === 'number') {
      current.total += value;
      total += value;
      knownBalanceCount += 1;
    }

    byType.set(type, current);

    if (account.balance?.error) {
      balanceErrors.push(`${account.name}: ${account.balance.error}`);
    }
  }

  const lines = ['# Sequence Balance Summary', ''];
  if (requestId) lines.push(`Request ID: \`${requestId}\``, '');

  lines.push(`Total known balance: **${cents(total)}**`);
  lines.push(`Accounts returned: **${accounts.length}**`);
  lines.push(`Accounts with known balances: **${knownBalanceCount}**`);
  lines.push('');
  lines.push('## By Type');

  for (const [type, summary] of [...byType.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    lines.push(`- **${type}**: ${cents(summary.total)} across ${summary.count} account${summary.count === 1 ? '' : 's'}`);
  }

  if (balanceErrors.length > 0) {
    lines.push('', '## Errors');
    for (const error of balanceErrors) lines.push(`- ${error}`);
  }

  return lines.join('\n');
}

export function findAccount(accounts: SequenceAccountSummary[], query: string): SequenceAccountSummary[] {
  const normalized = query.trim().toLowerCase();
  return accounts.filter((account) => {
    return account.id.toLowerCase() === normalized || account.name.toLowerCase().includes(normalized);
  });
}

export function formatTransfers(transfers: SequenceTransfer[], requestId?: string): string {
  const lines = ['# Sequence Transfers', ''];
  if (requestId) lines.push(`Request ID: \`${requestId}\``, '');

  if (transfers.length === 0) {
    lines.push('No transfers returned.');
    return lines.join('\n');
  }

  for (const transfer of transfers) {
    const from = transfer.source?.name || 'External/unknown source';
    const to = transfer.destination?.name || 'External/unknown destination';
    lines.push(`- **${cents(transfer.amountInCents)}** ${from} -> ${to} (${transfer.direction}, ${transfer.origin}, ${transfer.status}) - ${transfer.createdAt} - \`${transfer.id}\``);
    if (transfer.ruleExecutionId) lines.push(`  Rule execution: \`${transfer.ruleExecutionId}\``);
    if (transfer.errorCode) lines.push(`  Error: ${transfer.errorCode}`);
  }

  return lines.join('\n');
}

export function formatRules(rules: SequenceRule[], requestId?: string): string {
  const lines = ['# Sequence Rules', ''];
  if (requestId) lines.push(`Request ID: \`${requestId}\``, '');

  if (rules.length === 0) {
    lines.push('No rules returned.');
    return lines.join('\n');
  }

  for (const rule of rules) {
    const supported = rule.isSupported === false ? 'unsupported by public API' : 'supported';
    lines.push(`- **${rule.name}** (${rule.status}, ${supported}) - \`${rule.id}\``);
    if (rule.description) lines.push(`  ${rule.description}`);
  }

  return lines.join('\n');
}

export function formatRuleExecutions(executions: SequenceRuleExecution[], requestId?: string): string {
  const lines = ['# Sequence Rule Executions', ''];
  if (requestId) lines.push(`Request ID: \`${requestId}\``, '');

  if (executions.length === 0) {
    lines.push('No rule executions returned.');
    return lines.join('\n');
  }

  for (const execution of executions) {
    lines.push(`- **${execution.status}** - ${execution.createdAt} - \`${execution.id}\``);
    if (execution.transfersAttempted !== undefined) {
      lines.push(`  Transfers: ${execution.transfersCompleted ?? 0} completed, ${execution.transfersPending ?? 0} pending, ${execution.transfersFailed ?? 0} failed, ${execution.transfersAttempted} attempted`);
    }
    if (execution.errorCode || execution.errorMessage) {
      lines.push(`  Error: ${[execution.errorCode, execution.errorMessage].filter(Boolean).join(' - ')}`);
    }
  }

  return lines.join('\n');
}
