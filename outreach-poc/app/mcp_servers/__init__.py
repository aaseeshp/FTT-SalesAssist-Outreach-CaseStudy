"""Mock SalesAssist capability servers exposed over MCP (stdio).

Each server stands in for an existing SalesAssist capability:
  salesassist-crm      Unified intelligence: profile + CRM activity; Proactive prioritisation: signals
  salesassist-book     Recent sales and holdings
  salesassist-content  Product documents and fund reference data (compliance-filtered)
  salesassist-admin    Administrative support (scheduling helpers; read-only for agents)

Security model: the signed-in user is injected by the host process via the SALESASSIST_USER_ID
environment variable when the server is spawned. Tools never accept a user id from the model,
so an agent cannot widen its own region scope.
"""
