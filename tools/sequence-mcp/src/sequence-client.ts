export type SequenceBalance = {
  balanceInCents: number | null;
  availableBalanceInCents: number | null;
  lastStatementBalanceInCents: number | null;
  lastStatementDate?: string | null;
  nextPaymentMinimumInCents: number | null;
  nextPaymentDueDate?: string | null;
  balanceLastUpdatedAt: string | null;
  error: string | null;
  interestRatePercentage?: number | null;
  originalLoanAmountInCents?: number | null;
};

export type SequenceAccountSummary = {
  id: string;
  name: string;
  type: string;
  description?: string | null;
  externalAccountType?: string | null;
  beneficiaryName?: string | null;
  institutionName?: string | null;
  canBeSource?: boolean;
  createdAt?: string;
  updatedAt?: string;
  deletedAt?: string | null;
};

export type SequenceAccount = SequenceAccountSummary & {
  routingNumber?: string | null;
  bankAccountNumber?: string | null;
  balance?: SequenceBalance | null;
};

export type SequenceTransfer = {
  id: string;
  amountInCents: number;
  direction: string;
  origin: string;
  status: string;
  source?: SequenceAccountNode | null;
  destination?: SequenceAccountNode | null;
  ruleId?: string | null;
  ruleExecutionId?: string | null;
  errorCode?: string | null;
  createdAt: string;
  completedAt?: string | null;
};

export type SequenceAccountNode = {
  id: string;
  name: string;
  type: string;
  isDeleted?: boolean;
};

export type SequenceRule = {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  isSupported?: boolean;
  createdAt?: string;
  updatedAt?: string;
  deletedAt?: string | null;
};

export type SequenceRuleExecution = {
  id: string;
  ruleId: string;
  status: string;
  triggerType?: string;
  createdAt: string;
  completedAt?: string | null;
  transfersAttempted?: number;
  transfersCompleted?: number;
  transfersFailed?: number;
  transfersPending?: number;
  transferIds?: string[];
  errorCode?: string | null;
  errorMessage?: string | null;
};

export type SequenceApiResponse<T> = {
  requestId?: string;
  data?: T;
  error?: {
    code?: string;
    message?: string;
  };
};

export class SequenceClient {
  constructor(
    private readonly apiKey: string,
    private readonly baseUrl = 'https://api.getsequence.io/platform/v1'
  ) {}

  private async request<T>(path: string, params?: Record<string, string | number | undefined>): Promise<{
    data: T;
    requestId?: string;
    raw: SequenceApiResponse<T>;
  }> {
    const url = new URL(`${this.baseUrl.replace(/\/$/, '')}${path}`);
    for (const [key, value] of Object.entries(params || {})) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }

    const response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'x-called-reason': 'Codex finance MCP read-only account, balance, rule, and transfer lookup',
      },
    });

    const raw = (await response.json().catch(() => ({}))) as SequenceApiResponse<T>;

    if (!response.ok) {
      const code = raw.error?.code ? ` (${raw.error.code})` : '';
      const message = raw.error?.message ? ` ${raw.error.message}` : '';
      const requestId = raw.requestId ? ` requestId=${raw.requestId}` : '';
      const authHint = response.status === 401
        ? ' Check that SEQUENCE_API_KEY is a Platform API key from Settings -> API Keys.'
        : '';
      throw new Error(`Sequence ${path} failed: HTTP ${response.status}${code}.${message}${requestId}${authHint}`);
    }

    if (raw.data === undefined) {
      throw new Error(`Sequence ${path} returned no data.${raw.requestId ? ` requestId=${raw.requestId}` : ''}`);
    }

    return {
      data: raw.data,
      requestId: raw.requestId,
      raw,
    };
  }

  async listAccounts(params: { type?: string; page?: number; pageSize?: number } = {}) {
    const response = await this.request<{
      items: SequenceAccountSummary[];
      pagination: { page: number; pageSize: number };
    }>('/accounts', {
      type: params.type,
      page: params.page || 1,
      pageSize: params.pageSize || 100,
    });

    return {
      accounts: response.data.items,
      pagination: response.data.pagination,
      requestId: response.requestId,
      raw: response.raw,
    };
  }

  async getAccount(id: string) {
    const response = await this.request<SequenceAccount>(`/accounts/${encodeURIComponent(id)}`);
    return {
      account: response.data,
      requestId: response.requestId,
      raw: response.raw,
    };
  }

  async listAccountDetails(params: { type?: string } = {}) {
    const listed = await this.listAccounts({ type: params.type, pageSize: 100 });
    const accounts = await Promise.all(listed.accounts.map((account) => this.getAccount(account.id).then((result) => result.account)));
    return {
      accounts,
      requestId: listed.requestId,
      raw: { listed: listed.raw, accounts },
    };
  }

  async listTransfers(accountId: string, params: {
    accountRole?: string;
    direction?: string;
    status?: string;
    from?: string;
    to?: string;
    origin?: string;
    rule_execution_id?: string;
    page?: number;
    pageSize?: number;
  } = {}) {
    const response = await this.request<{
      items: SequenceTransfer[];
      pagination: { page: number; pageSize: number };
    }>(`/accounts/${encodeURIComponent(accountId)}/transfers`, {
      accountRole: params.accountRole,
      direction: params.direction,
      status: params.status,
      from: params.from,
      to: params.to,
      origin: params.origin,
      rule_execution_id: params.rule_execution_id,
      page: params.page || 1,
      pageSize: params.pageSize || 50,
    });

    return {
      transfers: response.data.items,
      pagination: response.data.pagination,
      requestId: response.requestId,
      raw: response.raw,
    };
  }

  async getTransfer(id: string) {
    const response = await this.request<SequenceTransfer>(`/transfers/${encodeURIComponent(id)}`);
    return {
      transfer: response.data,
      requestId: response.requestId,
      raw: response.raw,
    };
  }

  async listRules(params: { sourceId?: string; page?: number; pageSize?: number } = {}) {
    const response = await this.request<{
      items: SequenceRule[];
      pagination: { page: number; pageSize: number };
    }>('/rules', {
      sourceId: params.sourceId,
      page: params.page || 1,
      pageSize: params.pageSize || 100,
    });

    return {
      rules: response.data.items,
      pagination: response.data.pagination,
      requestId: response.requestId,
      raw: response.raw,
    };
  }

  async listRuleExecutions(ruleId: string, params: {
    status?: string;
    triggerType?: string;
    from?: string;
    to?: string;
    page?: number;
    pageSize?: number;
  } = {}) {
    const response = await this.request<{
      items: SequenceRuleExecution[];
      pagination: { page: number; pageSize: number };
    }>(`/rules/${encodeURIComponent(ruleId)}/executions`, {
      status: params.status,
      triggerType: params.triggerType,
      from: params.from,
      to: params.to,
      page: params.page || 1,
      pageSize: params.pageSize || 50,
    });

    return {
      executions: response.data.items,
      pagination: response.data.pagination,
      requestId: response.requestId,
      raw: response.raw,
    };
  }
}
