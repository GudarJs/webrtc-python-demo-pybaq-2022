import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:webrtcapp/src/screens/screens.dart';
import 'package:webrtcapp/src/providers/providers.dart';

void main() => runApp(new MyApp());

class MyApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [ChangeNotifierProvider(create: (_) => DetectionProvider())],
      child:
          MaterialApp(debugShowCheckedModeBanner: false, home: VideoScreen()),
    );
  }
}
