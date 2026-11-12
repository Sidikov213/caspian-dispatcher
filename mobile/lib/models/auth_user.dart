enum AuthRole {
  logist,
  expeditor;

  String get apiValue => switch (this) {
    AuthRole.logist => 'logist',
    AuthRole.expeditor => 'expeditor',
  };

  String get label => switch (this) {
    AuthRole.logist => 'Логист',
    AuthRole.expeditor => 'Экспедист',
  };

  static AuthRole fromApi(String? raw) => switch (raw) {
    'expeditor' => AuthRole.expeditor,
    _ => AuthRole.logist,
  };
}

class AuthUser {
  const AuthUser({
    required this.id,
    required this.name,
    required this.email,
    required this.role,
  });

  final String id;
  final String name;
  final String email;
  final AuthRole role;

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      id: '${json['id'] ?? ''}',
      name: '${json['name'] ?? ''}',
      email: '${json['email'] ?? ''}',
      role: AuthRole.fromApi(json['role']?.toString()),
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'email': email,
    'role': role.apiValue,
  };
}

class AuthSession {
  const AuthSession({required this.token, required this.user});

  final String token;
  final AuthUser user;

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      token: '${json['token'] ?? ''}',
      user: AuthUser.fromJson(
        Map<String, dynamic>.from(json['user'] as Map? ?? const {}),
      ),
    );
  }
}
