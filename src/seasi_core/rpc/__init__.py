"""JSON-RPC stdio surface (business channel for the despacho shell)."""

from seasi_core.rpc.server import Dispatcher, RpcError, serve, serve_stdio

__all__ = ["Dispatcher", "RpcError", "serve", "serve_stdio"]
