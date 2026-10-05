import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// LORAI mobile client (каркас, этап EXCELLENCE 2/2.5).
/// Требует Flutter 3.x + backend на http://<host>:8000.
/// Статус: BLOCKED до установки тулчейна (см. mobile/README.md, DECISIONS #15).
void main() => runApp(const LoraiApp());

class Api {
  static String base = 'http://10.0.2.2:8000';
  static String? token;

  static Map<String, String> get headers => {
        'Content-Type': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  static Future<Map<String, dynamic>> chat(String message) async {
    final r = await http.post(Uri.parse('$base/chat'),
        headers: headers, body: jsonEncode({'message': message}));
    if (r.statusCode != 200) throw Exception('chat ${r.statusCode}');
    return jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> login(String email, String password) async {
    final r = await http.post(Uri.parse('$base/login'),
        headers: headers,
        body: jsonEncode({'email': email, 'password': password}));
    if (r.statusCode != 200) throw Exception('login ${r.statusCode}');
    return jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
  }
}

class LoraiApp extends StatelessWidget {
  const LoraiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'LORAI',
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.teal),
      home: const ChatScreen(),
    );
  }
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _ctl = TextEditingController();
  final List<Map<String, String>> _msgs = [];
  bool _busy = false;
  String? _err;

  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    final p = await SharedPreferences.getInstance();
    setState(() => Api.token = p.getString('token'));
  }

  Future<void> _send() async {
    final text = _ctl.text.trim();
    if (text.isEmpty || _busy) return;
    setState(() {
      _msgs.add({'role': 'user', 'text': text});
      _busy = true;
      _err = null;
      _ctl.clear();
    });
    try {
      final res = await Api.chat(text);
      setState(() => _msgs.add({
            'role': 'bot',
            'text': (res['answer'] ?? res.toString()).toString(),
          }));
    } catch (e) {
      setState(() => _err = e.toString());
    } finally {
      setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('LORAI — чат')),
      body: Column(
        children: [
          const Padding(
            padding: EdgeInsets.all(8),
            child: Text(
              'Справочник по клиническим рекомендациям. Решение принимает врач.',
              style: TextStyle(fontSize: 12),
            ),
          ),
          if (_err != null)
            Padding(
              padding: const EdgeInsets.all(8),
              child: Text(_err!, style: const TextStyle(color: Colors.red)),
            ),
          Expanded(
            child: ListView.builder(
              itemCount: _msgs.length,
              itemBuilder: (c, i) {
                final m = _msgs[i];
                final me = m['role'] == 'user';
                return Align(
                  alignment: me ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 4),
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: me
                          ? Theme.of(context).colorScheme.primaryContainer
                          : Theme.of(context).colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(m['text'] ?? ''),
                  ),
                );
              },
            ),
          ),
          if (_busy) const LinearProgressIndicator(),
          Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _ctl,
                    decoration: const InputDecoration(
                      hintText: 'Вопрос по ЛОР-протоколам…',
                      border: OutlineInputBorder(),
                    ),
                    onSubmitted: (_) => _send(),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filled(
                  onPressed: _busy ? null : _send,
                  icon: const Icon(Icons.send),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
