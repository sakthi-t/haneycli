# Roadmap

Haney is under active development. This document outlines the planned direction and future capabilities.

## Completed

All phases through the current release are implemented and stable:

- ✅ CLI foundation (Typer, Rich, commands, setup wizard)
- ✅ Multi-provider support (6 providers via LiteLLM)
- ✅ Live model fetching from provider APIs
- ✅ Streaming LLM responses with Rich Markdown rendering
- ✅ Exa web search integration
- ✅ Project awareness (auto-discovery of plan.md, memory.md, summary.md, README.md)
- ✅ File attachment system (`@file` syntax, 119 supported extensions)
- ✅ Safe tool system (read, write, edit, rename, trash-based delete, shell execution)
- ✅ Session management (JSON archives, token tracking, cost estimation)
- ✅ Memory system (memory.md + summary.md, /remember, /compact)
- ✅ Thinking modes (off/low/medium/high, unified provider abstraction)
- ✅ Plan/Edit modes (discussion vs. execution)
- ✅ Permission modes (ASK/SAVE/AUTO, session-scoped approval memory)
- ✅ Configuration-driven architecture (no hardcoded limits)
- ✅ Sticky input composer with status bar
- ✅ Rich terminal experience (streaming, tool status, cost display)

## Short-Term

Features planned for upcoming releases:

### MCP (Model Context Protocol) Support

Integrate with Anthropic's Model Context Protocol to allow Haney to connect to external tools and data sources through a standardized interface. This would enable:

- Database connections
- API integrations
- External service queries
- Custom tool servers

### Autonomous Agent Workflows

Allow the LLM to plan and execute multi-step tasks autonomously within safety constraints:

- Multi-file refactoring
- Test generation and execution
- Documentation generation
- Dependency updates

### Additional Search Providers

Expand beyond Exa to support:

- Tavily
- Brave Search
- Google Custom Search
- Perplexity

Each provider would be selectable via `search_provider` in config.json.

### Improved Session Restoration

Allow users to resume previous sessions:

- Load conversation history from archived JSON
- Restore project context state
- Continue where they left off

## Medium-Term

### Git Integration

Deep Git awareness:

- Automatic commit message generation
- PR review and summarization
- Diff-aware editing
- Branch-aware context
- Changelog generation

### Voice Input

Terminal-based voice transcription for hands-free coding:

- Wake word detection
- Real-time transcription
- Natural language code editing

### Plugin System

Extensible tool architecture:

- Community-contributed tools
- Tool marketplace
- Custom provider integrations
- Plugin sandboxing

### Multi-Modal Support

- Image understanding (beyond metadata)
- Diagram generation from descriptions
- Screenshot-to-code workflows
- PDF parsing and analysis

## Long-Term

### Collaborative Sessions

- Shared sessions between developers
- Role-based access control
- Session merging and conflict resolution
- Team memory and conventions

### IDE Integration

- VS Code extension
- JetBrains plugin
- Direct file system watching
- Inline code suggestions

### Local-First AI

- Local model support via Ollama and llama.cpp
- Offline-first architecture
- Privacy-preserving code assistance
- On-device inference for sensitive projects

### Autonomous Debugging

- Test failure analysis
- Stack trace interpretation
- Automated fix proposals
- Regression testing

## Design Principles (Forward-Looking)

As Haney evolves, these principles guide development:

1. **Transparency over magic.** Every action should be visible and explainable.
2. **Configuration over convention.** Behavior belongs in config, not buried in code.
3. **Safety by default.** New features ship in restricted mode first.
4. **Local-first.** Core functionality works without cloud dependencies.
5. **Terminal-native.** The terminal is the primary interface. GUIs are secondary.
6. **Modular.** Each subsystem is independently testable and replaceable.

## Contributing

Haney welcomes contributions that align with these principles. Areas where help is especially valuable:

- Provider integrations (new LLM backends)
- Tool implementations (new safe operations)
- Documentation and examples
- Test coverage
- Platform-specific improvements (Windows, macOS)

See the GitHub repository for contribution guidelines.
