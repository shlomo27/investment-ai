import React, { useEffect, useState } from "react";
import { useAppSelector } from "../store";
import { ordersApi } from "../api/client";
import { Order, OrderStatus, OrderType } from "../types";

const Orders: React.FC = () => {
  const { user } = useAppSelector((state) => state.auth);
  const isHe = user?.preferred_language === "he";
  const [orders, setOrders] = useState<Order[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [filter, setFilter] = useState<string>("ALL");

  useEffect(() => {
    fetchOrders();
  }, [filter]);

  const fetchOrders = async () => {
    setIsLoading(true);
    try {
      const data = await ordersApi.getOrders(filter === "ALL" ? undefined : filter);
      setOrders(data);
    } catch (e) {
      console.error(e);
    }
    setIsLoading(false);
  };

  const exportCSV = () => {
    if (!orders.length) return;
    const headers = isHe
      ? ['סמל', 'סוג', 'כמות', 'מחיר', 'סה"כ', 'סטטוס', 'תאריך']
      : ['Symbol', 'Type', 'Quantity', 'Price', 'Total', 'Status', 'Date'];
    const rows = orders.map(o => [
      o.symbol,
      o.order_type,
      o.quantity,
      (o.executed_price ?? o.price_at_order).toFixed(2),
      (o.executed_total ?? o.total_amount).toFixed(2),
      o.status,
      o.created_at ? new Date(o.created_at).toLocaleDateString() : '',
    ]);
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `orders-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCancel = async (orderId: number) => {
    if (!window.confirm(isHe ? "האם לבטל את ההזמנה?" : "Cancel this order?")) return;
    try {
      await ordersApi.cancelOrder(orderId);
      fetchOrders();
    } catch (e: any) {
      alert(e.response?.data?.detail || "Cancel failed");
    }
  };

  const statusBadge = (status: OrderStatus) => {
    const map: Record<OrderStatus, { label: string; color: string }> = {
      [OrderStatus.EXECUTED]: { label: "EXECUTED", color: "bg-green-800 text-green-300" },
      [OrderStatus.PENDING]: { label: "PENDING", color: "bg-yellow-800 text-yellow-300" },
      [OrderStatus.CANCELLED]: { label: "CANCELLED", color: "bg-gray-700 text-gray-400" },
      [OrderStatus.REJECTED]: { label: "REJECTED", color: "bg-red-800 text-red-300" },
      [OrderStatus.PARTIALLY_FILLED]: { label: "PARTIAL", color: "bg-blue-800 text-blue-300" },
    };
    const s = map[status] || { label: status, color: "bg-gray-700 text-gray-400" };
    return <span className={`text-xs px-2 py-0.5 rounded ${s.color}`}>{s.label}</span>;
  };

  const filters = ["ALL", "EXECUTED", "PENDING", "CANCELLED", "REJECTED"];

  return (
    <div dir={isHe ? "rtl" : "ltr"} className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{isHe ? "היסטוריית עסקאות" : "Trade History"}</h1>
        <button
          onClick={exportCSV}
          disabled={!orders.length}
          className="no-print text-sm bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 rounded-xl px-4 py-2 flex items-center gap-2 disabled:opacity-40"
        >
          <span>📥</span>{isHe ? "ייצוא CSV" : "Export CSV"}
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 flex-wrap">
        {filters.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-1.5 rounded-lg text-sm border transition-colors ${
              filter === f
                ? "bg-blue-600 border-blue-500 text-white"
                : "border-gray-700 text-gray-400 hover:border-gray-600"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-gray-900 rounded-2xl animate-pulse" />
          ))}
        </div>
      ) : orders.length === 0 ? (
        <div className="bg-gray-900 rounded-2xl p-12 border border-gray-800 text-center text-gray-500">
          <p className="text-4xl mb-3">📋</p>
          <p>{isHe ? "אין עסקאות" : "No orders found"}</p>
        </div>
      ) : (
        <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800">
                {["Symbol", "Type", "Qty", "Price", "Total", "Status", "Date", ""].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs text-gray-400 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="px-4 py-3 font-bold">{order.symbol}</td>
                  <td className="px-4 py-3">
                    <span className={`text-sm font-medium ${order.order_type === OrderType.BUY ? "text-green-400" : "text-red-400"}`}>
                      {order.order_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm">{order.quantity.toFixed(4)}</td>
                  <td className="px-4 py-3 text-sm">
                    ₪{(order.executed_price || order.price_at_order).toLocaleString("en", { minimumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3 text-sm font-medium">
                    ₪{(order.executed_total || order.total_amount).toLocaleString("en", { minimumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3">{statusBadge(order.status)}</td>
                  <td className="px-4 py-3 text-xs text-gray-400">
                    {new Date(order.created_at).toLocaleDateString(isHe ? "he-IL" : "en-US")}
                  </td>
                  <td className="px-4 py-3">
                    {order.status === OrderStatus.PENDING && (
                      <button
                        onClick={() => handleCancel(order.id)}
                        className="text-xs text-red-400 hover:text-red-300 border border-red-800 px-2 py-1 rounded"
                      >
                        {isHe ? "ביטול" : "Cancel"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default Orders;
